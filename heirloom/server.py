"""A tiny local web server (standard library only) that serves the interface
and a JSON API over the Store. It listens on 127.0.0.1 only, so nothing is
reachable from other computers."""

import base64
import io
import json
import mimetypes
import os
import re
import sqlite3
import tempfile
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import db as dbmod
from .db import Store, NotFound, Invalid
from .gedcom import import_gedcom, export_gedcom
from .kinship import relationship
from .sample import load_sample

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
MAX_BODY = 200 * 1024 * 1024  # 200 MB, enough for a large photo or GEDCOM


class Api:
    """Routes: (method, regex) -> handler(match, query, body) -> (status, payload)."""

    def __init__(self, store):
        self.s = store
        self.lock = threading.Lock()
        self.routes = []
        r = self.route
        r("GET", r"/api/meta", self.meta)
        r("PUT", r"/api/meta", self.set_meta)
        r("GET", r"/api/graph", lambda m, q, b: self.s.graph())
        r("GET", r"/api/people", lambda m, q, b: self.s.list_people())
        r("POST", r"/api/people", lambda m, q, b: self.s.get_person(self.s.save_person(b)))
        r("GET", r"/api/people/(\d+)", lambda m, q, b: self.s.get_person(int(m[1])))
        r("PUT", r"/api/people/(\d+)", lambda m, q, b: self.s.get_person(self.s.save_person(b, int(m[1]))))
        r("DELETE", r"/api/people/(\d+)", lambda m, q, b: self.s.delete_person(int(m[1])))
        r("POST", r"/api/links", lambda m, q, b: {"id": self.s.add_parent_link(
            b["child_id"], b["parent_id"], b.get("kind", "biological"), b.get("date", ""), b.get("notes", ""))})
        r("PUT", r"/api/links/(\d+)", lambda m, q, b: self.s.update_parent_link(int(m[1]), b))
        r("DELETE", r"/api/links/(\d+)", lambda m, q, b: self.s.delete_parent_link(int(m[1])))
        r("POST", r"/api/couples", lambda m, q, b: {"id": self.s.save_couple(b)})
        r("PUT", r"/api/couples/(\d+)", lambda m, q, b: {"id": self.s.save_couple(b, int(m[1]))})
        r("DELETE", r"/api/couples/(\d+)", lambda m, q, b: self.s.delete_couple(int(m[1])))
        r("GET", r"/api/stories", lambda m, q, b: self.s.list_stories())
        r("POST", r"/api/stories", lambda m, q, b: self.s.get_story(self.s.save_story(b)))
        r("GET", r"/api/stories/(\d+)", lambda m, q, b: self.s.get_story(int(m[1])))
        r("PUT", r"/api/stories/(\d+)", lambda m, q, b: self.s.get_story(self.s.save_story(b, int(m[1]))))
        r("DELETE", r"/api/stories/(\d+)", lambda m, q, b: self.s.delete_story(int(m[1])))
        r("GET", r"/api/media", lambda m, q, b: self.s.list_media())
        r("POST", r"/api/media", self.upload)
        r("PUT", r"/api/media/(\d+)", lambda m, q, b: self.s.update_media(int(m[1]), b))
        r("DELETE", r"/api/media/(\d+)", lambda m, q, b: self.s.delete_media(int(m[1])))
        r("GET", r"/api/relationship", self.rel)
        r("POST", r"/api/import-gedcom", lambda m, q, b: import_gedcom(self.s, b.get("text", "")))
        r("POST", r"/api/sample", self.sample)

    def route(self, method, pattern, fn):
        self.routes.append((method, re.compile(pattern + "$"), fn))

    def dispatch(self, method, path, query, body):
        for meth, rx, fn in self.routes:
            m = rx.match(path)
            if m and meth == method:
                with self.lock:
                    return fn(m, query, body)
        raise NotFound("no such endpoint")

    def meta(self, m, q, b):
        return {
            "family_name": self.s.get_meta("family_name", "Our Family"),
            "empty": self.s.is_empty(),
            "data_dir": self.s.data_dir,
            "kinds": {"parent": dbmod.PARENT_KINDS, "couple": dbmod.COUPLE_KINDS,
                      "end": dbmod.END_REASONS, "name": dbmod.NAME_KINDS, "fact": dbmod.FACT_KINDS},
        }

    def set_meta(self, m, q, b):
        if "family_name" in b:
            self.s.set_meta("family_name", str(b["family_name"]).strip()[:120] or "Our Family")
        return self.meta(m, q, b)

    def upload(self, m, q, b):
        raw = base64.b64decode(b["data"].split(",", 1)[-1])
        mid = self.s.add_media(raw, b.get("mime", ""), b.get("name", ""), b.get("caption", ""),
                               b.get("date", ""), b.get("person_ids", []))
        return self.s.get_media(mid)

    def rel(self, m, q, b):
        return relationship(self.s.graph(), int(q["a"][0]), int(q["b"][0]))

    def sample(self, m, q, b):
        if not self.s.is_empty():
            raise Invalid("The sample family can only be loaded into an empty tree.")
        load_sample(self.s)
        return {"ok": True}


def make_handler(api):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Heirloom/1.0"

        def log_message(self, fmt, *args):  # keep the console quiet
            pass

        # -- helpers
        def send(self, status, body=b"", ctype="application/json", extra=None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def send_json(self, status, payload):
            self.send(status, json.dumps(payload, default=str).encode("utf-8"))

        def host_ok(self):
            # Refuse requests whose Host isn't this machine (guards against DNS rebinding).
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
            return host in ("localhost", "127.0.0.1", "::1")

        def handle_any(self, method):
            if not self.host_ok():
                return self.send(403, b"Forbidden", "text/plain")
            url = urlparse(self.path)
            path, query = url.path, parse_qs(url.query)
            try:
                if path.startswith("/api/"):
                    return self.api(method, path, query)
                if method == "GET" and path.startswith("/photo/"):
                    return self.photo(path)
                if method == "GET":
                    return self.static(path)
                self.send_json(405, {"error": "method not allowed"})
            except BrokenPipeError:
                pass

        def api(self, method, path, query):
            body = {}
            if method in ("POST", "PUT"):
                if "application/json" not in (self.headers.get("Content-Type") or ""):
                    return self.send_json(415, {"error": "JSON required"})
                n = int(self.headers.get("Content-Length") or 0)
                if n > MAX_BODY:
                    return self.send_json(413, {"error": "That file is too large."})
                try:
                    body = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return self.send_json(400, {"error": "bad JSON"})
            if method == "GET" and path == "/api/export.ged":
                text = export_gedcom(api.s).encode("utf-8")
                return self.send(200, text, "text/plain; charset=utf-8",
                                 {"Content-Disposition": 'attachment; filename="family-tree.ged"'})
            if method == "GET" and path == "/api/backup.zip":
                return self.send(200, backup_zip(api.s), "application/zip",
                                 {"Content-Disposition": 'attachment; filename="family-tree-backup.zip"'})
            try:
                result = api.dispatch(method, path, query, body)
                self.send_json(200, result if result is not None else {"ok": True})
            except NotFound as e:
                self.send_json(404, {"error": str(e)})
            except (Invalid, KeyError, ValueError, TypeError) as e:
                self.send_json(400, {"error": str(e) or "invalid request"})
            except sqlite3.Error as e:
                self.send_json(400, {"error": f"database: {e}"})

        def photo(self, path):
            m = re.match(r"^/photo/(\d+)$", path)
            if not m:
                return self.send(404, b"", "text/plain")
            try:
                fpath, mime = api.s.media_path(int(m[1]))
                with open(fpath, "rb") as fh:
                    data = fh.read()
            except (NotFound, OSError):
                return self.send(404, b"", "text/plain")
            self.send(200, data, mime)

        def static(self, path):
            if path in ("/", ""):
                path = "/index.html"
            full = os.path.realpath(os.path.join(STATIC_DIR, path.lstrip("/")))
            if not full.startswith(os.path.realpath(STATIC_DIR)) or not os.path.isfile(full):
                return self.send(404, b"Not found", "text/plain")
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            with open(full, "rb") as fh:
                self.send(200, fh.read(), ctype)

        def do_GET(self):
            self.handle_any("GET")

        def do_HEAD(self):
            self.handle_any("GET")

        def do_POST(self):
            self.handle_any("POST")

        def do_PUT(self):
            self.handle_any("PUT")

        def do_DELETE(self):
            self.handle_any("DELETE")

    return Handler


def backup_zip(store):
    """A zip of a consistent copy of the database plus every photo."""
    buf = io.BytesIO()
    with tempfile.TemporaryDirectory() as tmp:
        copy_path = os.path.join(tmp, "family.db")
        dest = sqlite3.connect(copy_path)
        store.conn.backup(dest)
        dest.close()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(copy_path, "family.db")
            for name in sorted(os.listdir(store.media_dir)):
                z.write(os.path.join(store.media_dir, name), f"photos/{name}")
            z.writestr("family-tree.ged", export_gedcom(store))
            z.writestr("README.txt",
                       "Heirloom backup.\n\nTo restore: put family.db and the photos folder in "
                       "your data folder (or run start_heirloom.py --data <this folder>).\n"
                       "family-tree.ged opens in any genealogy program.\n")
    return buf.getvalue()


def serve(data_dir, port=8765, host="127.0.0.1"):
    store = Store(data_dir)
    api = Api(store)
    handler = make_handler(api)
    last_error = None
    for p in range(port, port + 20):
        try:
            httpd = ThreadingHTTPServer((host, p), handler)
            return httpd, store
        except OSError as e:
            last_error = e
    raise last_error
