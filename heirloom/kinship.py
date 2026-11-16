"""Work out how two people are related.

Relationships are computed over two different "views" of the tree:

  genetic  - only biological (and donor) links: who shares blood.
  legal    - adoptive links, plus biological links an adoption didn't replace.
             A full adoption replaces both birth parents; a step-parent
             adoption replaces only the birth parent who isn't the adopter's
             partner.

So an adopted child who was born a second cousin shows up as "legally your
brother; by blood, your second cousin". On top of these, step, foster,
spouse and in-law relationships are found from the couples and other link
kinds.
"""

from collections import defaultdict

GENETIC_KINDS = {"biological", "donor"}
MAX_GENERATIONS = 40


# ---------------------------------------------------------------- views
def parent_sets(graph, mode):
    """child_id -> set(parent_id) for the given view ('genetic' or 'legal')."""
    by_child = defaultdict(list)
    for l in graph["links"]:
        by_child[l["child_id"]].append(l)
    partners = _partner_pairs(graph)
    out = defaultdict(set)
    for child, links in by_child.items():
        if mode == "genetic":
            out[child] = {l["parent_id"] for l in links if l["kind"] in GENETIC_KINDS}
        elif mode == "legal":
            adopters = {l["parent_id"] for l in links if l["kind"] == "adoptive"}
            bio = {l["parent_id"] for l in links if l["kind"] == "biological"}
            if not adopters:
                out[child] = bio
            else:
                kept = set()
                if len(adopters) == 1:
                    (adopter,) = adopters
                    kept = {b for b in bio if frozenset((b, adopter)) in partners}
                out[child] = adopters | kept
        else:
            raise ValueError(mode)
    return out


def _partner_pairs(graph):
    return {frozenset((c["partner1_id"], c["partner2_id"])) for c in graph["couples"]}


MAX_PATHS = 50000


def _ancestor_paths(pid, parents):
    """Every upward path from pid, as tuples (pid, parent, grandparent, ...).
    Paths, not just distances, so that when cousins marry (pedigree collapse)
    each separate line of descent is kept and named."""
    paths, stack = [], [(pid,)]
    while stack and len(paths) < MAX_PATHS:
        path = stack.pop()
        paths.append(path)
        if len(path) <= MAX_GENERATIONS:
            for par in parents.get(path[-1], ()):
                if par not in path:
                    stack.append(path + (par,))
    return paths


def blood_routes(a, b, parents):
    """List of (dA, dB, [ancestor ids]) for each distinct line of relationship.

    A line is a path up from A and a path up from B that meet at a common
    ancestor and share no one else - so a route that runs on past a closer
    shared ancestor doesn't count twice."""
    if a == b:
        return []
    b_paths = defaultdict(list)
    for p in _ancestor_paths(b, parents):
        b_paths[p[-1]].append(p)
    routes = defaultdict(set)
    for pa in _ancestor_paths(a, parents):
        top = pa[-1]
        for pb in b_paths.get(top, ()):
            if len(set(pa) & set(pb)) == 1:
                routes[(len(pa) - 1, len(pb) - 1)].add(top)
    return sorted(((da, db, sorted(ids)) for (da, db), ids in routes.items()),
                  key=lambda r: (r[0] + r[1], abs(r[0] - r[1])))


# ---------------------------------------------------------------- naming
_ORD = ["zeroth", "first", "second", "third", "fourth", "fifth", "sixth", "seventh",
        "eighth", "ninth", "tenth"]
_GENDERED = {
    "parent": ("father", "mother"), "child": ("son", "daughter"),
    "grandparent": ("grandfather", "grandmother"), "grandchild": ("grandson", "granddaughter"),
    "sibling": ("brother", "sister"), "aunt/uncle": ("uncle", "aunt"),
    "niece/nephew": ("nephew", "niece"), "spouse": ("husband", "wife"),
    "step-parent": ("stepfather", "stepmother"), "stepchild": ("stepson", "stepdaughter"),
    "step-sibling": ("stepbrother", "stepsister"),
    "parent-in-law": ("father-in-law", "mother-in-law"),
    "child-in-law": ("son-in-law", "daughter-in-law"),
    "sibling-in-law": ("brother-in-law", "sister-in-law"),
    "foster parent": ("foster father", "foster mother"),
    "foster child": ("foster son", "foster daughter"),
    "former spouse": ("former husband", "former wife"),
}


def ordinal(n):
    return _ORD[n] if n < len(_ORD) else f"{n}th"


def _nth(n):
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def great(n):
    return "" if n <= 0 else "great-" if n == 1 else "great-great-" if n == 2 else f"{_nth(n)} great-"


def gender(term, sex):
    """'sibling' + 'F' -> 'sister'. Works on the last word-group of a phrase."""
    for base, (m, f) in sorted(_GENDERED.items(), key=lambda kv: -len(kv[0])):
        if term.endswith(base):
            word = m if sex == "M" else f if sex == "F" else base
            return term[: -len(base)] + word
    return term


def name_route(da, db, sex="U", half=False):
    """What B is to A, given A is da generations below the common ancestor and B is db."""
    h = "half-" if half else ""
    if da == 0:  # B descends from A
        base = "child" if db == 1 else "grandchild" if db == 2 else great(db - 2) + "grandchild"
        return gender(base, sex)
    if db == 0:  # B is A's ancestor
        base = "parent" if da == 1 else "grandparent" if da == 2 else great(da - 2) + "grandparent"
        return gender(base, sex)
    if da == 1 and db == 1:
        return h + gender("sibling", sex)
    if db == 1:  # B is a sibling of A's ancestor
        return h + gender(great(da - 2) + "aunt/uncle", sex)
    if da == 1:  # B descends from A's sibling
        return h + gender(great(db - 2) + "niece/nephew", sex)
    c, r = min(da, db) - 1, abs(da - db)
    removed = "" if r == 0 else " once removed" if r == 1 else " twice removed" if r == 2 \
        else f" {r} times removed"
    return f"{'half ' if half else ''}{ordinal(c)} cousin{removed}"


def describe_routes(routes, sex, people, couples):
    out = []
    for da, db, anc in routes:
        half = False
        if da and db:
            # Full relationship needs two common ancestors who are a couple.
            half = not any(frozenset((x, y)) in couples for x in anc for y in anc if x != y)
        out.append({
            "label": name_route(da, db, sex, half),
            "up": da, "down": db, "half": half,
            "via": [people[i]["display_name"] for i in anc if i in people],
        })
    return out


# ---------------------------------------------------------------- main entry
def relationship(graph, a, b):
    people = {p["id"]: p for p in graph["people"]}
    if a not in people or b not in people:
        raise KeyError("unknown person")
    pa, pb = people[a], people[b]
    sex_b = pb.get("sex", "U")
    couples = _partner_pairs(graph)
    result = {"a": pa["display_name"], "b": pb["display_name"],
              "genetic": [], "legal": [], "other": [], "summary": ""}
    if a == b:
        result["summary"] = "That's the same person."
        return result

    gen_parents = parent_sets(graph, "genetic")
    leg_parents = parent_sets(graph, "legal")
    result["genetic"] = describe_routes(blood_routes(a, b, gen_parents), sex_b, people, couples)
    result["legal"] = describe_routes(blood_routes(a, b, leg_parents), sex_b, people, couples)
    blood = bool(result["genetic"] or result["legal"])
    result["other"] = _other_relations(graph, a, b, people, leg_parents, gen_parents, blood)
    result["summary"] = _summarize(result, pa, pb)
    return result


def _first_label(rels):
    return rels[0]["label"] if rels else None


def _summarize(r, pa, pb):
    A, B = pa["display_name"], pb["display_name"]
    leg, gen = _first_label(r["legal"]), _first_label(r["genetic"])
    parts = []
    if leg and gen and leg == gen:
        parts.append(f"{B} is {A}'s {leg}.")
        extra = [x["label"] for x in r["genetic"][1:]]
        if extra:
            parts.append(f"They are also related through another line: {', '.join(extra)}.")
    elif leg and gen:
        lr, gr = r["legal"][0], r["genetic"][0]
        legal_txt = f"through adoption, {B} is {A}'s {leg}"
        blood_txt = f"by blood, {B} is {A}'s {gen}"
        first, second = (legal_txt, blood_txt) if lr["up"] + lr["down"] <= gr["up"] + gr["down"] \
            else (blood_txt, legal_txt)
        parts.append(first[0].upper() + first[1:] + "; " + second + ".")
    elif leg:
        parts.append(f"{B} is {A}'s {leg} (through adoption). They aren't related by blood.")
    elif gen:
        parts.append(f"By blood, {B} is {A}'s {gen}.")
        parts.append("An adoption means this isn't a legal relationship.")
    if r["other"]:
        lead = "" if parts else f"{B} is {A}'s "
        if parts:
            parts.append(f"{B} is also {A}'s " + "; ".join(r["other"]) + ".")
        else:
            parts.append(lead + "; ".join(r["other"]) + ".")
    if not parts:
        parts.append(f"No relationship between {A} and {B} is recorded yet.")
    return " ".join(parts)


def _other_relations(graph, a, b, people, leg_parents, gen_parents, blood=False):
    sex_b = people[b].get("sex", "U")
    out = []

    # Direct, non-blood links (step, foster, guardian, surrogate) in either direction.
    for l in graph["links"]:
        if l["kind"] in ("biological", "adoptive", "donor"):
            continue
        if l["child_id"] == a and l["parent_id"] == b:
            term = {"step": "step-parent", "foster": "foster parent", "guardian": "guardian",
                    "surrogate": "surrogate (birth) mother", "unknown": "parent (link type unknown)"}
            out.append(gender(term[l["kind"]], sex_b))
        elif l["child_id"] == b and l["parent_id"] == a:
            term = {"step": "stepchild", "foster": "foster child", "guardian": "ward",
                    "surrogate": "child carried as surrogate", "unknown": "child (link type unknown)"}
            out.append(gender(term[l["kind"]], sex_b))

    # Spouses / partners.
    partners_of = defaultdict(list)
    for c in graph["couples"]:
        partners_of[c["partner1_id"]].append((c["partner2_id"], c))
        partners_of[c["partner2_id"]].append((c["partner1_id"], c))
    for other, c in partners_of[a]:
        if other == b:
            ended = c["end_reason"] in ("divorce", "annulment", "separation")
            if c["kind"] in ("marriage", "civil union"):
                out.append(gender("former spouse" if ended else "spouse", sex_b))
            else:
                out.append(("former " if ended else "") + c["kind"] + " partner")

    all_parents = lambda x: leg_parents.get(x, set()) | gen_parents.get(x, set())

    # Step relations inferred from couples (if not already stated directly).
    if not any(o.startswith(("step", "stepf", "stepm")) for o in out):
        pa_par, pb_par = all_parents(a), all_parents(b)
        if b not in pa_par and any(b in [o for o, _ in partners_of[p]] for p in pa_par):
            out.append(gender("step-parent", sex_b))
        elif a not in pb_par and any(a in [o for o, _ in partners_of[p]] for p in pb_par):
            out.append(gender("stepchild", sex_b))
        elif pa_par and pb_par and not (pa_par & pb_par) and any(
                frozenset((x, y)) in _partner_pairs(graph) for x in pa_par for y in pb_par):
            out.append(gender("step-sibling", sex_b))

    # In-laws: B is married to A's relative, or B is A's spouse's relative.
    for parents in (leg_parents, gen_parents):
        for rel, _ in partners_of[b]:
            if rel in (a,):
                continue
            routes = blood_routes(a, rel, parents)
            if routes:
                da, db, _ = routes[0]
                if (da, db) == (1, 0):
                    continue  # married to A's parent: a step-parent, handled above
                if (da, db) == (1, 1):
                    out.append(gender("sibling-in-law", sex_b))
                elif (da, db) == (0, 1):
                    out.append(gender("child-in-law", sex_b))
                else:
                    rel_sex = people[rel].get("sex", "U")
                    if not blood:  # e.g. a grandmother's husband who is also a grandfather
                        out.append(f"{name_route(da, db, rel_sex)}'s spouse")
        for sp, _ in partners_of[a]:
            if sp == b:
                continue
            routes = blood_routes(sp, b, parents)
            if routes:
                da, db, _ = routes[0]
                if (da, db) == (0, 1):
                    continue  # spouse's child: a stepchild, handled above
                if (da, db) == (1, 0):
                    out.append(gender("parent-in-law", sex_b))
                elif (da, db) == (1, 1):
                    out.append(gender("sibling-in-law", sex_b))
                else:
                    if not blood:
                        out.append(f"spouse's {name_route(da, db, sex_b)}")
    # De-duplicate, keep order.
    seen, uniq = set(), []
    for o in out:
        if o not in seen:
            seen.add(o)
            uniq.append(o)
    return uniq
