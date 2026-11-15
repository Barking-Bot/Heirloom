"""Storage for Heirloom: one SQLite file plus a folder of photos.

The central idea: relationships are typed links, not fixed slots.
  * A person records the name they were born with (so a maiden name is
    never lost) plus any later names.
  * A couple (marriage, partnership...) is its own record, so people can
    have any number of them, each with a start, an end and a reason.
  * Each parent-child link carries a kind: biological, adoptive, step,
    foster, guardian, donor or surrogate. A child may have any number of
    them, so birth parents and adoptive parents sit side by side.
"""

import os
import re
import sqlite3
import datetime

SCHEMA_VERSION = 1

SEXES = ("M", "F", "X", "U")
PARENT_KINDS = ("biological", "adoptive", "step", "foster", "guardian",
                "donor", "surrogate", "unknown")
COUPLE_KINDS = ("marriage", "civil union", "partnership", "engagement", "other")
END_REASONS = ("", "divorce", "death", "annulment", "separation", "other")
NAME_KINDS = ("married", "adopted", "changed", "nickname", "religious", "alias")
FACT_KINDS = ("occupation", "residence", "education", "military", "religion",
              "immigration", "emigration", "naturalization", "baptism",
              "burial", "cause of death", "other")

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS media (
  id INTEGER PRIMARY KEY,
  filename TEXT NOT NULL,
  original_name TEXT NOT NULL DEFAULT '',
  mime TEXT NOT NULL DEFAULT '',
  caption TEXT NOT NULL DEFAULT '',
  date TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS person (
  id INTEGER PRIMARY KEY,
  given_names TEXT NOT NULL DEFAULT '',
  birth_surname TEXT NOT NULL DEFAULT '',
  sex TEXT NOT NULL DEFAULT 'U',
  birth_date TEXT NOT NULL DEFAULT '',
  birth_place TEXT NOT NULL DEFAULT '',
  deceased INTEGER NOT NULL DEFAULT 0,
  death_date TEXT NOT NULL DEFAULT '',
  death_place TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  portrait_id INTEGER REFERENCES media(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alt_name (
  id INTEGER PRIMARY KEY,
  person_id INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  kind TEXT NOT NULL DEFAULT 'married',
  given_names TEXT NOT NULL DEFAULT '',
  surname TEXT NOT NULL DEFAULT '',
  from_date TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS couple (
  id INTEGER PRIMARY KEY,
  partner1_id INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  partner2_id INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  kind TEXT NOT NULL DEFAULT 'marriage',
  start_date TEXT NOT NULL DEFAULT '',
  start_place TEXT NOT NULL DEFAULT '',
  end_date TEXT NOT NULL DEFAULT '',
  end_reason TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  CHECK (partner1_id <> partner2_id)
);

CREATE TABLE IF NOT EXISTS parent_link (
  id INTEGER PRIMARY KEY,
  child_id INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  parent_id INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  kind TEXT NOT NULL DEFAULT 'biological',
  date TEXT NOT NULL DEFAULT '',
  notes TEXT NOT NULL DEFAULT '',
  CHECK (child_id <> parent_id),
  UNIQUE (child_id, parent_id, kind)
);

CREATE TABLE IF NOT EXISTS fact (
  id INTEGER PRIMARY KEY,
  person_id INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  kind TEXT NOT NULL DEFAULT 'other',
  date TEXT NOT NULL DEFAULT '',
  place TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS story (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL DEFAULT '',
  body TEXT NOT NULL DEFAULT '',
  date TEXT NOT NULL DEFAULT '',
  told_by TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS story_person (
  story_id INTEGER NOT NULL REFERENCES story(id) ON DELETE CASCADE,
  person_id INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  PRIMARY KEY (story_id, person_id)
);

CREATE TABLE IF NOT EXISTS media_person (
  media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
  person_id INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  PRIMARY KEY (media_id, person_id)
);

CREATE INDEX IF NOT EXISTS ix_link_child ON parent_link(child_id);
CREATE INDEX IF NOT EXISTS ix_link_parent ON parent_link(parent_id);
CREATE INDEX IF NOT EXISTS ix_couple_p1 ON couple(partner1_id);
CREATE INDEX IF NOT EXISTS ix_couple_p2 ON couple(partner2_id);
"""

_YEAR = re.compile(r"(\d{4})")


def year_of(date_text):
    """Best-effort year from free-text dates like '1923', 'abt 1923', '5 Apr 1923'."""
    m = _YEAR.search(date_text or "")
    return int(m.group(1)) if m else None


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


class NotFound(Exception):
    pass


class Invalid(Exception):
    pass


def _clean(data, fields, enums=None):
    """Keep only known text fields, trimmed; check enum fields."""
    out = {}
    for f in fields:
        if f in data:
            v = data[f]
            out[f] = "" if v is None else str(v).strip()
    for f, allowed in (enums or {}).items():
        if f in out and out[f] not in allowed:
            raise Invalid(f"{f} must be one of: {', '.join(a or '(blank)' for a in allowed)}")
    return out


class Store:
    def __init__(self, data_dir):
        self.data_dir = os.path.abspath(data_dir)
        self.media_dir = os.path.join(self.data_dir, "photos")
        os.makedirs(self.media_dir, exist_ok=True)
        self.path = os.path.join(self.data_dir, "family.db")
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)",
                          (str(SCHEMA_VERSION),))
        self.conn.commit()

    # ---------- safety ----------
    def _stamp(self):
        return datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")

    def auto_backup(self, keep=15):
        """Copy the database into backups/ (called at every start). Keeps the newest `keep`."""
        if self.is_empty():
            return None
        bdir = os.path.join(self.data_dir, "backups")
        os.makedirs(bdir, exist_ok=True)
        dest_path = os.path.join(bdir, f"family-{self._stamp()}.db")
        dest = sqlite3.connect(dest_path)
        self.conn.backup(dest)
        dest.close()
        old = sorted(f for f in os.listdir(bdir) if f.startswith("family-") and f.endswith(".db"))
        for f in old[:-keep]:
            try:
                os.remove(os.path.join(bdir, f))
            except OSError:
                pass
        return dest_path

    def _set_aside(self, filename):
        """Move a photo into backups/removed-photos instead of deleting it."""
        src = os.path.join(self.media_dir, filename)
        if not os.path.isfile(src):
            return
        dst_dir = os.path.join(self.data_dir, "backups", "removed-photos")
        os.makedirs(dst_dir, exist_ok=True)
        os.replace(src, os.path.join(dst_dir, f"{self._stamp()}-{filename}"))

    def clear_all(self):
        """Empty the tree (after taking a backup). Used to remove the example family."""
        self.auto_backup(keep=30)
        for m in self.q("SELECT filename FROM media"):
            self._set_aside(m["filename"])
        for t in ("story_person", "media_person", "story", "fact", "alt_name", "parent_link",
                  "couple", "person", "media"):
            self.conn.execute(f"DELETE FROM {t}")
        self.conn.execute("DELETE FROM meta WHERE key IN ('sample', 'family_name')")
        self.conn.commit()

    # ---------- helpers ----------
    def q(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        r = self.conn.execute(sql, args).fetchone()
        return dict(r) if r else None

    def _exists(self, table, id_):
        if not self.one(f"SELECT id FROM {table} WHERE id=?", (id_,)):
            raise NotFound(f"{table} {id_} not found")

    def is_empty(self):
        return self.one("SELECT COUNT(*) AS n FROM person")["n"] == 0

    def get_meta(self, key, default=""):
        r = self.one("SELECT value FROM meta WHERE key=?", (key,))
        return r["value"] if r else default

    def set_meta(self, key, value):
        self.conn.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, value))
        self.conn.commit()

    # ---------- people ----------
    PERSON_FIELDS = ("given_names", "birth_surname", "sex", "birth_date", "birth_place",
                     "death_date", "death_place", "notes")

    def _summaries(self, where="", args=()):
        people = self.q(f"""SELECT id, given_names, birth_surname, sex, birth_date,
                              birth_place, deceased, death_date, death_place, portrait_id
                            FROM person {where}""", args)
        if not people:
            return []
        names = {}
        for n in self.q("SELECT * FROM alt_name ORDER BY id"):
            names.setdefault(n["person_id"], []).append(n)
        for p in people:
            p["deceased"] = bool(p["deceased"])
            p["alt_names"] = names.get(p["id"], [])
            p.update(display_names(p))
            p["birth_year"] = year_of(p["birth_date"])
            p["death_year"] = year_of(p["death_date"])
        return people

    def list_people(self):
        people = self._summaries()
        people.sort(key=lambda p: (p["surname"].lower(), p["given_names"].lower(), p["id"]))
        return people

    def summary(self, pid):
        s = self._summaries("WHERE id=?", (pid,))
        if not s:
            raise NotFound(f"person {pid} not found")
        return s[0]

    def get_person(self, pid):
        p = self.one("SELECT * FROM person WHERE id=?", (pid,))
        if not p:
            raise NotFound(f"person {pid} not found")
        p.update(self.summary(pid))
        p["facts"] = self.q("SELECT * FROM fact WHERE person_id=? ORDER BY id", (pid,))
        p["parents"] = [dict(l, person=self.summary(l["parent_id"])) for l in
                        self.q("SELECT * FROM parent_link WHERE child_id=? ORDER BY id", (pid,))]
        p["children"] = [dict(l, person=self.summary(l["child_id"])) for l in
                         self.q("SELECT * FROM parent_link WHERE parent_id=? ORDER BY id", (pid,))]
        p["children"].sort(key=lambda l: (l["person"]["birth_year"] or 9999, l["person"]["id"]))
        couples = self.q("SELECT * FROM couple WHERE partner1_id=? OR partner2_id=?", (pid, pid))
        for c in couples:
            other = c["partner2_id"] if c["partner1_id"] == pid else c["partner1_id"]
            c["partner"] = self.summary(other)
        couples.sort(key=lambda c: (year_of(c["start_date"]) or 9999, c["id"]))
        p["couples"] = couples
        p["stories"] = self.q("""SELECT s.id, s.title, s.date FROM story s
                                 JOIN story_person sp ON sp.story_id=s.id
                                 WHERE sp.person_id=? ORDER BY s.date, s.id""", (pid,))
        p["media"] = self.q("""SELECT m.* FROM media m JOIN media_person mp ON mp.media_id=m.id
                               WHERE mp.person_id=? ORDER BY m.date, m.id""", (pid,))
        return p

    def save_person(self, data, pid=None):
        f = _clean(data, self.PERSON_FIELDS, {"sex": SEXES})
        if "deceased" in data:
            f["deceased"] = 1 if data["deceased"] else 0
        if f.get("death_date") or f.get("death_place"):
            f["deceased"] = 1
        if "portrait_id" in data:
            f["portrait_id"] = data["portrait_id"] or None
        now = _now()
        if pid is None:
            f.setdefault("given_names", "")
            cols = list(f) + ["created_at", "updated_at"]
            cur = self.conn.execute(
                f"INSERT INTO person ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                [*f.values(), now, now])
            pid = cur.lastrowid
        else:
            self._exists("person", pid)
            if f:
                sets = ",".join(f"{k}=?" for k in f)
                self.conn.execute(f"UPDATE person SET {sets}, updated_at=? WHERE id=?",
                                  [*f.values(), now, pid])
        if "alt_names" in data:
            self.conn.execute("DELETE FROM alt_name WHERE person_id=?", (pid,))
            for n in data["alt_names"] or []:
                n = _clean(n, ("kind", "given_names", "surname", "from_date", "notes"),
                           {"kind": NAME_KINDS})
                if n.get("surname") or n.get("given_names"):
                    self.conn.execute("""INSERT INTO alt_name (person_id, kind, given_names,
                        surname, from_date, notes) VALUES (?,?,?,?,?,?)""",
                        (pid, n.get("kind", "married"), n.get("given_names", ""),
                         n.get("surname", ""), n.get("from_date", ""), n.get("notes", "")))
        if "facts" in data:
            self.conn.execute("DELETE FROM fact WHERE person_id=?", (pid,))
            for x in data["facts"] or []:
                x = _clean(x, ("kind", "date", "place", "detail"), {"kind": FACT_KINDS})
                if any(x.get(k) for k in ("date", "place", "detail")):
                    self.conn.execute("""INSERT INTO fact (person_id, kind, date, place, detail)
                        VALUES (?,?,?,?,?)""", (pid, x.get("kind", "other"), x.get("date", ""),
                                                 x.get("place", ""), x.get("detail", "")))
        self.conn.commit()
        return pid

    def delete_person(self, pid):
        self._exists("person", pid)
        self.conn.execute("DELETE FROM person WHERE id=?", (pid,))
        self.conn.commit()

    # ---------- parent links ----------
    def add_parent_link(self, child_id, parent_id, kind="biological", date="", notes=""):
        child_id, parent_id = int(child_id), int(parent_id)
        if kind not in PARENT_KINDS:
            raise Invalid(f"kind must be one of: {', '.join(PARENT_KINDS)}")
        if child_id == parent_id:
            raise Invalid("A person can't be their own parent.")
        self._exists("person", child_id)
        self._exists("person", parent_id)
        if self._is_ancestor(child_id, parent_id):
            raise Invalid("That would make someone their own ancestor.")
        try:
            cur = self.conn.execute("""INSERT INTO parent_link (child_id, parent_id, kind, date, notes)
                                       VALUES (?,?,?,?,?)""", (child_id, parent_id, kind, date, notes))
        except sqlite3.IntegrityError:
            raise Invalid("That link already exists.")
        self.conn.commit()
        return cur.lastrowid

    def _is_ancestor(self, maybe_ancestor, pid):
        """True if pid is already a descendant of maybe_ancestor (via any kind of link),
        so making pid a parent of maybe_ancestor would create a loop."""
        seen, stack = set(), [maybe_ancestor]
        while stack:
            cur = stack.pop()
            for r in self.conn.execute("SELECT child_id FROM parent_link WHERE parent_id=?", (cur,)):
                c = r[0]
                if c == pid:
                    return True
                if c not in seen:
                    seen.add(c)
                    stack.append(c)
        return False

    def update_parent_link(self, link_id, data):
        self._exists("parent_link", link_id)
        f = _clean(data, ("kind", "date", "notes"), {"kind": PARENT_KINDS})
        if f:
            sets = ",".join(f"{k}=?" for k in f)
            try:
                self.conn.execute(f"UPDATE parent_link SET {sets} WHERE id=?", [*f.values(), link_id])
            except sqlite3.IntegrityError:
                raise Invalid("That link already exists.")
            self.conn.commit()

    def delete_parent_link(self, link_id):
        self._exists("parent_link", link_id)
        self.conn.execute("DELETE FROM parent_link WHERE id=?", (link_id,))
        self.conn.commit()

    # ---------- couples ----------
    COUPLE_FIELDS = ("kind", "start_date", "start_place", "end_date", "end_reason", "notes")

    def save_couple(self, data, cid=None):
        f = _clean(data, self.COUPLE_FIELDS, {"kind": COUPLE_KINDS, "end_reason": END_REASONS})
        if cid is None:
            a, b = int(data["partner1_id"]), int(data["partner2_id"])
            if a == b:
                raise Invalid("Pick two different people.")
            self._exists("person", a)
            self._exists("person", b)
            cols = ["partner1_id", "partner2_id", *f]
            cur = self.conn.execute(
                f"INSERT INTO couple ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                [a, b, *f.values()])
            cid = cur.lastrowid
        else:
            self._exists("couple", cid)
            if f:
                sets = ",".join(f"{k}=?" for k in f)
                self.conn.execute(f"UPDATE couple SET {sets} WHERE id=?", [*f.values(), cid])
        self.conn.commit()
        return cid

    def delete_couple(self, cid):
        self._exists("couple", cid)
        self.conn.execute("DELETE FROM couple WHERE id=?", (cid,))
        self.conn.commit()

    # ---------- stories ----------
    def list_stories(self):
        stories = self.q("SELECT * FROM story ORDER BY date, id")
        links = {}
        for r in self.q("SELECT * FROM story_person"):
            links.setdefault(r["story_id"], []).append(r["person_id"])
        for s in stories:
            s["person_ids"] = links.get(s["id"], [])
        return stories

    def get_story(self, sid):
        s = self.one("SELECT * FROM story WHERE id=?", (sid,))
        if not s:
            raise NotFound(f"story {sid} not found")
        s["person_ids"] = [r["person_id"] for r in
                           self.q("SELECT person_id FROM story_person WHERE story_id=?", (sid,))]
        return s

    def save_story(self, data, sid=None):
        f = _clean(data, ("title", "body", "date", "told_by"))
        now = _now()
        if sid is None:
            cols = [*f, "created_at", "updated_at"]
            cur = self.conn.execute(
                f"INSERT INTO story ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                [*f.values(), now, now])
            sid = cur.lastrowid
        else:
            self._exists("story", sid)
            sets = ",".join(f"{k}=?" for k in f)
            self.conn.execute(f"UPDATE story SET {sets}{',' if sets else ''} updated_at=? WHERE id=?",
                              [*f.values(), now, sid])
        if "person_ids" in data:
            self.conn.execute("DELETE FROM story_person WHERE story_id=?", (sid,))
            for pid in set(int(x) for x in data["person_ids"] or []):
                self._exists("person", pid)
                self.conn.execute("INSERT INTO story_person VALUES (?,?)", (sid, pid))
        self.conn.commit()
        return sid

    def delete_story(self, sid):
        self._exists("story", sid)
        self.conn.execute("DELETE FROM story WHERE id=?", (sid,))
        self.conn.commit()

    # ---------- photos ----------
    ALLOWED_IMAGES = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
                      "image/webp": ".webp", "image/heic": ".heic"}

    def add_media(self, raw_bytes, mime, original_name="", caption="", date="", person_ids=()):
        if mime not in self.ALLOWED_IMAGES:
            raise Invalid("Photos must be JPEG, PNG, GIF, WebP or HEIC.")
        cur = self.conn.execute("""INSERT INTO media (filename, original_name, mime, caption, date,
                                   created_at) VALUES ('',?,?,?,?,?)""",
                                (original_name, mime, caption, date, _now()))
        mid = cur.lastrowid
        filename = f"{mid:06d}{self.ALLOWED_IMAGES[mime]}"
        with open(os.path.join(self.media_dir, filename), "wb") as fh:
            fh.write(raw_bytes)
        self.conn.execute("UPDATE media SET filename=? WHERE id=?", (filename, mid))
        for pid in set(int(x) for x in person_ids):
            self._exists("person", pid)
            self.conn.execute("INSERT INTO media_person VALUES (?,?)", (mid, pid))
        self.conn.commit()
        return mid

    def get_media(self, mid):
        m = self.one("SELECT * FROM media WHERE id=?", (mid,))
        if not m:
            raise NotFound(f"photo {mid} not found")
        m["person_ids"] = [r["person_id"] for r in
                           self.q("SELECT person_id FROM media_person WHERE media_id=?", (mid,))]
        return m

    def list_media(self):
        media = self.q("SELECT * FROM media ORDER BY date, id")
        links = {}
        for r in self.q("SELECT * FROM media_person"):
            links.setdefault(r["media_id"], []).append(r["person_id"])
        for m in media:
            m["person_ids"] = links.get(m["id"], [])
        return media

    def update_media(self, mid, data):
        self._exists("media", mid)
        f = _clean(data, ("caption", "date"))
        if f:
            sets = ",".join(f"{k}=?" for k in f)
            self.conn.execute(f"UPDATE media SET {sets} WHERE id=?", [*f.values(), mid])
        if "person_ids" in data:
            self.conn.execute("DELETE FROM media_person WHERE media_id=?", (mid,))
            for pid in set(int(x) for x in data["person_ids"] or []):
                self._exists("person", pid)
                self.conn.execute("INSERT INTO media_person VALUES (?,?)", (mid, pid))
        self.conn.commit()

    def delete_media(self, mid):
        m = self.get_media(mid)
        self.conn.execute("DELETE FROM media WHERE id=?", (mid,))
        self.conn.commit()
        try:
            self._set_aside(m["filename"])
        except OSError:
            pass

    def media_path(self, mid):
        m = self.get_media(mid)
        return os.path.join(self.media_dir, m["filename"]), m["mime"]

    # ---------- whole graph ----------
    def graph(self):
        return {
            "people": self.list_people(),
            "links": self.q("SELECT id, child_id, parent_id, kind FROM parent_link"),
            "couples": self.q("SELECT * FROM couple"),
        }


def display_names(p):
    """Current surname = most recent married/changed/adopted name, else birth surname."""
    surname = p.get("birth_surname", "")
    given = p.get("given_names", "")
    later = [n for n in p.get("alt_names", []) if n["kind"] in ("married", "changed", "adopted")]
    if later:
        later.sort(key=lambda n: (year_of(n["from_date"]) or 0, n["id"]))
        last = later[-1]
        surname = last["surname"] or surname
        given = last["given_names"] or given
    full = " ".join(x for x in (given, surname) if x) or "(unnamed)"
    nee = p.get("birth_surname", "") if surname != p.get("birth_surname", "") else ""
    return {"display_name": full, "surname": surname, "nee": nee}
