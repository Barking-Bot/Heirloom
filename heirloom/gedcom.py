"""GEDCOM import and export.

GEDCOM is the standard file that Ancestry, FamilySearch, MyHeritage and
most genealogy programs can export. On import, adoption and foster
information is read from all the places programs put it: PEDI tags, ADOP
events, and Ancestry's _FREL/_MREL tags.
"""

import re
import datetime
from collections import defaultdict

from .db import FACT_KINDS, NAME_KINDS

# ------------------------------------------------------------------ parsing
_LINE = re.compile(r"^\s*(\d+)\s+(?:(@[^@]+@)\s+)?(\S+)(?:\s(.*))?$")


class Node:
    __slots__ = ("level", "xref", "tag", "value", "children")

    def __init__(self, level, xref, tag, value):
        self.level, self.xref, self.tag, self.value = level, xref, tag, value
        self.children = []

    def first(self, tag):
        for c in self.children:
            if c.tag == tag:
                return c
        return None

    def all(self, tag):
        return [c for c in self.children if c.tag == tag]

    def val(self, tag, default=""):
        c = self.first(tag)
        return c.value if c else default


def parse(text):
    """Return a list of level-0 records."""
    text = text.lstrip("﻿")
    roots, stack = [], []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        m = _LINE.match(raw)
        if not m:
            continue
        level, xref, tag, value = int(m.group(1)), m.group(2), m.group(3).upper(), m.group(4) or ""
        while stack and stack[-1].level >= level:
            stack.pop()
        if tag in ("CONC", "CONT") and stack:
            parent = stack[-1]
            parent.value += ("\n" if tag == "CONT" else "") + value
            continue
        node = Node(level, xref, tag, value)
        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)
    return roots


# ------------------------------------------------------------------ import
_KIND_WORDS = {
    "birth": "biological", "natural": "biological", "biological": "biological",
    "adopted": "adoptive", "adoptive": "adoptive", "foster": "foster", "step": "step",
    "guardian": "guardian", "sealing": "biological", "private": "biological",
    "unknown": "unknown",
}


def _kind(word):
    return _KIND_WORDS.get((word or "").strip().lower())


def _split_name(value):
    """'John Henry /Smith/ Jr.' -> ('John Henry Jr.', 'Smith')."""
    m = re.match(r"^(.*?)/(.*?)/(.*)$", value or "")
    if not m:
        return (value or "").strip(), ""
    given = " ".join(x.strip() for x in (m.group(1), m.group(3)) if x.strip())
    return given, m.group(2).strip()


_FACT_TAGS = {"OCCU": "occupation", "RESI": "residence", "EDUC": "education",
              "RELI": "religion", "IMMI": "immigration", "EMIG": "emigration",
              "NATU": "naturalization", "BAPM": "baptism", "CHR": "baptism",
              "BURI": "burial", "_MILT": "military", "_MILTID": "military"}


def import_gedcom(store, text):
    records = parse(text)
    notes = {r.xref: r.value for r in records if r.tag == "NOTE" and r.xref}

    shared_note_people = defaultdict(list)  # shared NOTE records become stories

    def note_text(n):
        v = n.value.strip()
        return notes.get(v, v) if v.startswith("@") else v

    def own_notes(rec):
        return "\n\n".join(note_text(n) for n in rec.all("NOTE")
                           if not n.value.strip().startswith("@") and note_text(n))

    indi_ids = {}
    pedi = {}            # (indi_xref, fam_xref) -> kind
    adopted_by = {}      # (indi_xref, fam_xref) -> 'BOTH' | 'HUSB' | 'WIFE'
    counts = defaultdict(int)

    for r in records:
        if r.tag != "INDI":
            continue
        names = r.all("NAME")
        primary = next((n for n in names if n.val("TYPE").lower() == "birth"), names[0] if names else None)
        given, surname = _split_name(primary.value) if primary else ("", "")
        if primary and not given:
            given = primary.val("GIVN")
        if primary and not surname:
            surname = primary.val("SURN")
        alt = []
        for n in names:
            if n is primary:
                continue
            g, s = _split_name(n.value)
            t = n.val("TYPE").lower()
            kind = "alias" if t in ("aka", "also known as") else t if t in NAME_KINDS else "changed"
            alt.append({"kind": kind, "given_names": g if g != given else "", "surname": s,
                        "from_date": n.val("DATE")})
        for n in (primary.all("_MARNM") if primary else []) + r.all("_MARNM"):
            alt.append({"kind": "married", "surname": _split_name(n.value)[1] or n.value.strip()})

        birt, deat = r.first("BIRT"), r.first("DEAT")
        facts = []
        for c in r.children:
            if c.tag in _FACT_TAGS:
                facts.append({"kind": _FACT_TAGS[c.tag], "date": c.val("DATE"),
                              "place": c.val("PLAC"), "detail": c.value})
            elif c.tag in ("EVEN", "FACT"):
                t = c.val("TYPE").lower()
                facts.append({"kind": t if t in FACT_KINDS else "other", "date": c.val("DATE"),
                              "place": c.val("PLAC"),
                              "detail": (c.val("TYPE") + ": " if t not in FACT_KINDS and c.val("TYPE") else "") + c.value})
        note = own_notes(r)
        sex = r.val("SEX").upper()[:1]
        pid = store.save_person({
            "given_names": given, "birth_surname": surname,
            "sex": sex if sex in ("M", "F", "X") else "U",
            "birth_date": birt.val("DATE") if birt else "", "birth_place": birt.val("PLAC") if birt else "",
            "deceased": bool(deat), "death_date": deat.val("DATE") if deat else "",
            "death_place": deat.val("PLAC") if deat else "",
            "notes": note, "alt_names": alt, "facts": facts,
        })
        indi_ids[r.xref] = pid
        counts["people"] += 1
        for n in r.all("NOTE"):
            ref = n.value.strip()
            if ref.startswith("@") and ref in notes:
                shared_note_people[ref].append(pid)

        for famc in r.all("FAMC"):
            k = _kind(famc.val("PEDI"))
            if k:
                pedi[(r.xref, famc.value.strip())] = k
        for adop in r.all("ADOP"):
            fam = adop.first("FAMC")
            if fam:
                who = fam.val("ADOP", "BOTH").upper() or "BOTH"
                adopted_by[(r.xref, fam.value.strip())] = who

    for r in records:
        if r.tag != "FAM":
            continue
        husb, wife = r.val("HUSB").strip(), r.val("WIFE").strip()
        h, w = indi_ids.get(husb), indi_ids.get(wife)
        if h and w:
            marr, div = r.first("MARR"), r.first("DIV")
            end_date, end_reason = "", ""
            if div:
                end_date, end_reason = div.val("DATE"), "divorce"
            store.save_couple({
                "partner1_id": h, "partner2_id": w,
                "kind": "marriage" if (marr or div) else "partnership",
                "start_date": marr.val("DATE") if marr else "",
                "start_place": marr.val("PLAC") if marr else "",
                "end_date": end_date, "end_reason": end_reason,
                "notes": own_notes(r),
            })
            counts["couples"] += 1
        for chil in r.all("CHIL"):
            cx = chil.value.strip()
            cid = indi_ids.get(cx)
            if not cid:
                continue
            base = pedi.get((cx, r.xref), "biological")
            adop = adopted_by.get((cx, r.xref))
            for role, parent_id, rel_tag in (("HUSB", h, "_FREL"), ("WIFE", w, "_MREL")):
                if not parent_id:
                    continue
                kind = _kind(chil.val(rel_tag)) or base
                if adop in ("BOTH", role):
                    kind = "adoptive"
                try:
                    store.add_parent_link(cid, parent_id, kind)
                    counts["parent links"] += 1
                except Exception:
                    counts["skipped links"] += 1

    for ref, pids in shared_note_people.items():
        text = notes[ref].strip()
        head, _, body = text.partition("\n")
        m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", head)
        title, date = (m.group(1), m.group(2)) if m else (head, "")
        body = body.strip()
        told_by = ""
        if body.startswith("Told by "):
            told_by, _, body = body.partition("\n")
            told_by = told_by[len("Told by "):]
            body = body.strip()
        store.save_story({"title": title[:200], "date": date, "told_by": told_by,
                          "body": body or text, "person_ids": pids})
        counts["stories"] += 1
    return dict(counts)


# ------------------------------------------------------------------ export
_PEDI_OUT = {"biological": "birth", "adoptive": "adopted", "foster": "foster"}
_REL_OUT = {"biological": "Natural", "adoptive": "Adopted", "foster": "Foster", "step": "Step",
            "guardian": "Guardian", "donor": "Natural", "surrogate": "Unknown", "unknown": "Unknown"}
_FACT_OUT = {v: k for k, v in _FACT_TAGS.items() if not k.startswith("_") and k != "CHR"}


def _lines(level, tag, value=""):
    """Emit a tag, splitting multi-line text into CONT lines."""
    parts = (value or "").split("\n")
    out = [f"{level} {tag}" + (f" {parts[0]}" if parts[0] else "")]
    out += [f"{level + 1} CONT {p}".rstrip() for p in parts[1:]]
    return out


def _event(level, tag, date, place):
    if not (date or place):
        return []
    out = [f"{level} {tag}"]
    if date:
        out.append(f"{level + 1} DATE {date}")
    if place:
        out.append(f"{level + 1} PLAC {place}")
    return out


def export_gedcom(store):
    people = {p["id"]: store.get_person(p["id"]) for p in store.list_people()}
    links = store.q("SELECT * FROM parent_link")
    couples = store.q("SELECT * FROM couple")
    stories = store.list_stories()

    # Families: one per couple, plus single-parent families for leftover links.
    fams = []  # dicts: id, husb, wife, couple, children: {child: {parent: kind}}
    by_child = defaultdict(dict)
    for l in links:
        by_child[l["child_id"]][l["parent_id"]] = l["kind"]
    for c in couples:
        a, b = c["partner1_id"], c["partner2_id"]
        if people[a]["sex"] == "F" and people[b]["sex"] != "F":
            a, b = b, a
        fams.append({"husb": a, "wife": b, "couple": c, "children": {}})
    covered = set()
    for child, parents in by_child.items():
        for f in fams:
            if f["husb"] in parents and f["wife"] in parents:
                f["children"][child] = parents
                covered.update({(child, f["husb"]), (child, f["wife"])})
    single = {}
    for child, parents in by_child.items():
        for par, kind in parents.items():
            if (child, par) in covered:
                continue
            if par not in single:
                f = {"husb": par, "wife": None, "couple": None, "children": {}}
                if people[par]["sex"] == "F":
                    f["husb"], f["wife"] = None, par
                single[par] = f
                fams.append(f)
            single[par]["children"][child] = {par: kind}
    for i, f in enumerate(fams, 1):
        f["xref"] = f"@F{i}@"

    famc = defaultdict(list)
    fams_of = defaultdict(list)
    for f in fams:
        for p in (f["husb"], f["wife"]):
            if p:
                fams_of[p].append(f["xref"])
        for child, parents in f["children"].items():
            kinds = {parents.get(p) for p in (f["husb"], f["wife"]) if p}
            k = "adoptive" if "adoptive" in kinds else "foster" if "foster" in kinds \
                else "biological" if kinds <= {"biological", "donor"} else None
            famc[child].append((f["xref"], _PEDI_OUT.get(k)))

    story_refs = defaultdict(list)
    for i, s in enumerate(stories, 1):
        for pid in s["person_ids"]:
            story_refs[pid].append(f"@N{i}@")

    out = ["0 HEAD", "1 SOUR HEIRLOOM", "2 NAME Heirloom family tree", "1 GEDC",
           "2 VERS 5.5.1", "2 FORM LINEAGE-LINKED", "1 CHAR UTF-8",
           f"1 DATE {datetime.date.today().strftime('%d %b %Y').upper()}"]

    for pid, p in people.items():
        out.append(f"0 @I{pid}@ INDI")
        out.append(f"1 NAME {p['given_names']} /{p['birth_surname']}/".replace("  ", " "))
        if p["given_names"]:
            out.append(f"2 GIVN {p['given_names']}")
        if p["birth_surname"]:
            out.append(f"2 SURN {p['birth_surname']}")
        out.append("2 TYPE birth")
        for n in p["alt_names"]:
            out.append(f"1 NAME {n['given_names'] or p['given_names']} /{n['surname']}/")
            out.append("2 TYPE " + ("aka" if n["kind"] == "alias" else n["kind"]))
            if n["from_date"]:
                out.append(f"2 DATE {n['from_date']}")
        out.append(f"1 SEX {p['sex']}")
        out += _event(1, "BIRT", p["birth_date"], p["birth_place"])
        if p["deceased"]:
            ev = _event(1, "DEAT", p["death_date"], p["death_place"])
            out += ev or ["1 DEAT Y"]
        for x in p["facts"]:
            tag = _FACT_OUT.get(x["kind"])
            if tag:
                out.append(f"1 {tag}" + (f" {x['detail']}" if x["detail"] and tag in ("OCCU", "EDUC", "RELI") else ""))
            else:
                out.append("1 EVEN" + (f" {x['detail']}" if x["detail"] else ""))
                out.append(f"2 TYPE {x['kind'].title()}")
            if x["date"]:
                out.append(f"2 DATE {x['date']}")
            if x["place"]:
                out.append(f"2 PLAC {x['place']}")
            if tag and x["detail"] and tag not in ("OCCU", "EDUC", "RELI"):
                out.append(f"2 NOTE {x['detail']}")
        if p["notes"]:
            out += _lines(1, "NOTE", p["notes"])
        for ref in story_refs[pid]:
            out.append(f"1 NOTE {ref}")
        for m in p["media"]:
            out.append("1 OBJE")
            out.append(f"2 FILE photos/{m['filename']}")
            out.append(f"3 FORM {m['filename'].rsplit('.', 1)[-1]}")
            if m["caption"]:
                out.append(f"3 TITL {m['caption']}")
        for xref, pedi in famc[pid]:
            out.append(f"1 FAMC {xref}")
            if pedi:
                out.append(f"2 PEDI {pedi}")
        for xref in fams_of[pid]:
            out.append(f"1 FAMS {xref}")

    for f in fams:
        out.append(f"0 {f['xref']} FAM")
        if f["husb"]:
            out.append(f"1 HUSB @I{f['husb']}@")
        if f["wife"]:
            out.append(f"1 WIFE @I{f['wife']}@")
        c = f["couple"]
        if c:
            if c["kind"] in ("marriage", "civil union"):
                out += _event(1, "MARR", c["start_date"], c["start_place"]) or ["1 MARR Y"]
            else:
                out.append(f"1 EVEN {c['start_date']}".rstrip())
                out.append(f"2 TYPE {c['kind'].title()}")
            if c["end_reason"] == "divorce":
                out += _event(1, "DIV", c["end_date"], "") or ["1 DIV Y"]
            elif c["end_reason"]:
                out.append(f"1 NOTE Ended ({c['end_reason']}) {c['end_date']}".rstrip())
            if c["notes"]:
                out += _lines(1, "NOTE", c["notes"])
        for child, parents in f["children"].items():
            out.append(f"1 CHIL @I{child}@")
            if f["husb"] in parents:
                out.append(f"2 _FREL {_REL_OUT[parents[f['husb']]]}")
            if f["wife"] in parents:
                out.append(f"2 _MREL {_REL_OUT[parents[f['wife']]]}")

    for i, s in enumerate(stories, 1):
        body = s["title"] + (f" ({s['date']})" if s["date"] else "")
        if s["told_by"]:
            body += f"\nTold by {s['told_by']}"
        body += "\n\n" + s["body"]
        out += _lines(0, f"@N{i}@ NOTE", body)

    out.append("0 TRLR")
    return "\n".join(out) + "\n"
