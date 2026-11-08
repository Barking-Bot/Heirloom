"use strict";
/* Heirloom front end: plain JavaScript, no libraries, so it keeps working
   for decades without a build step. */

// ------------------------------------------------------------------ basics
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const SVGNS = "http://www.w3.org/2000/svg";

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body === undefined && (method === "POST" || method === "PUT")) body = {};
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) throw new Error((data && data.error) || `Request failed (${res.status})`);
  return data;
}

let toastTimer;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 3200);
}

function store(key, value) {
  try {
    if (value === undefined) return localStorage.getItem(key);
    localStorage.setItem(key, value);
  } catch { return null; }
}

const KIND_LABEL = {
  biological: "Birth", adoptive: "Adopted", step: "Step", foster: "Foster",
  guardian: "Guardian", donor: "Donor", surrogate: "Surrogate", unknown: "Unknown",
};
const KIND_HELP = {
  biological: "Birth (biological) parent",
  adoptive: "Adoptive parent",
  step: "Step-parent (partner of a parent, not adopted)",
  foster: "Foster parent",
  guardian: "Legal guardian",
  donor: "Egg / sperm donor",
  surrogate: "Surrogate who carried the child",
  unknown: "Not sure yet",
};
const SEX_LABEL = { M: "Male", F: "Female", X: "Other", U: "Unknown" };

const state = {
  meta: null, graph: { people: [], links: [], couples: [] }, people: new Map(),
  focus: null, selected: null, up: 3, down: 3,
  view: { x: 40, y: 40, k: 1 }, layout: null, fitNext: true,
};

function lifespan(p) {
  const b = p.birth_year, d = p.death_year;
  if (b && d) return `${b}–${d}`;
  if (b) return p.deceased ? `${b}–?` : `b. ${b}`;
  if (d) return `d. ${d}`;
  return p.deceased ? "deceased" : "";
}
const nee = (p) => (p.sex === "F" ? "née" : "born");
const label = (p) => p.display_name + (lifespan(p) ? ` (${lifespan(p)})` : "");

// ------------------------------------------------------------------ data
async function refresh() {
  const [meta, graph] = await Promise.all([api("GET", "/api/meta"), api("GET", "/api/graph")]);
  state.meta = meta;
  state.graph = graph;
  state.people = new Map(graph.people.map((p) => [p.id, p]));
  $("#familyName").textContent = meta.family_name;
  document.title = `${meta.family_name} · Heirloom`;
  if (!state.people.has(state.focus)) {
    const saved = Number(store("heirloom.focus"));
    state.focus = state.people.has(saved) ? saved : pickDefaultFocus();
    state.fitNext = true;
  }
  if (state.selected && !state.people.has(state.selected)) closePanel();
  focusPicker.set(state.focus);
  renderTree();
  renderPeople();
  if ($("#tab-stories").classList.contains("active")) renderStories();
  if ($("#tab-photos").classList.contains("active")) renderPhotos();
  if (state.selected) openPanel(state.selected, true);
}

function pickDefaultFocus() {
  // The person with the most links is usually a good centre.
  let best = null, score = -1;
  const deg = new Map();
  for (const l of state.graph.links) {
    deg.set(l.child_id, (deg.get(l.child_id) || 0) + 1);
    deg.set(l.parent_id, (deg.get(l.parent_id) || 0) + 1);
  }
  for (const p of state.graph.people) {
    const s = deg.get(p.id) || 0;
    if (s > score) { best = p.id; score = s; }
  }
  return best;
}

function setFocus(id, { fit = true } = {}) {
  state.focus = id;
  store("heirloom.focus", String(id));
  focusPicker.set(id);
  state.fitNext = fit;
  renderTree();
}

// ------------------------------------------------------------------ person picker
function makePicker({ placeholder = "Type a name…", onPick = () => {}, exclude = () => false } = {}) {
  const wrap = document.createElement("div");
  wrap.className = "picker";
  wrap.innerHTML = `<input type="text" autocomplete="off" placeholder="${esc(placeholder)}"><div class="opts" hidden></div>`;
  const input = $("input", wrap), opts = $(".opts", wrap);
  let value = null, hi = 0, shown = [];

  function show() {
    const q = input.value.trim().toLowerCase();
    shown = state.graph.people.filter((p) => !exclude(p) &&
      (!q || `${p.display_name} ${p.nee} ${p.birth_surname} ${p.birth_year || ""}`.toLowerCase().includes(q)))
      .sort((a, b) => a.display_name.localeCompare(b.display_name)).slice(0, 40);
    hi = 0;
    opts.innerHTML = shown.length ? shown.map((p, i) =>
      `<div class="opt${i === 0 ? " hi" : ""}" data-i="${i}">${esc(p.display_name)}${p.nee ? ` <small>${nee(p)} ${esc(p.nee)}</small>` : ""} <small>${esc(lifespan(p))}</small></div>`).join("")
      : `<div class="opt muted">No matches</div>`;
    opts.hidden = false;
  }
  function choose(p) {
    value = p ? p.id : null;
    input.value = p ? label(p) : "";
    opts.hidden = true;
    onPick(value);
  }
  input.addEventListener("focus", () => { input.select(); show(); });
  input.addEventListener("input", show);
  input.addEventListener("blur", () => setTimeout(() => {
    opts.hidden = true;
    const p = state.people.get(value);
    input.value = p ? label(p) : "";
  }, 150));
  input.addEventListener("keydown", (e) => {
    if (opts.hidden) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      hi = Math.max(0, Math.min(shown.length - 1, hi + (e.key === "ArrowDown" ? 1 : -1)));
      $$(".opt", opts).forEach((o, i) => o.classList.toggle("hi", i === hi));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (shown[hi]) choose(shown[hi]);
    } else if (e.key === "Escape") {
      opts.hidden = true;
    }
  });
  opts.addEventListener("mousedown", (e) => {
    const o = e.target.closest(".opt[data-i]");
    if (o) { e.preventDefault(); choose(shown[Number(o.dataset.i)]); }
  });
  return {
    el: wrap,
    get value() { return value; },
    set(id) { value = id ?? null; const p = state.people.get(value); input.value = p ? label(p) : ""; },
    clear() { value = null; input.value = ""; },
    focus() { input.focus(); },
  };
}

function makeMultiPicker(initial = []) {
  const wrap = document.createElement("div");
  const chips = document.createElement("div");
  chips.className = "chips";
  let ids = [...initial];
  const pk = makePicker({
    placeholder: "Add a person…",
    exclude: (p) => ids.includes(p.id),
    onPick: (id) => { if (id && !ids.includes(id)) ids.push(id); pk.clear(); draw(); },
  });
  function draw() {
    chips.innerHTML = ids.map((id) => {
      const p = state.people.get(id);
      return p ? `<button type="button" class="chip" data-id="${id}">${esc(p.display_name)} <span class="x">×</span></button>` : "";
    }).join("");
  }
  chips.addEventListener("click", (e) => {
    const c = e.target.closest(".chip");
    if (c) { ids = ids.filter((x) => x !== Number(c.dataset.id)); draw(); }
  });
  wrap.append(pk.el, chips);
  draw();
  return { el: wrap, get value() { return ids; } };
}

// ------------------------------------------------------------------ tree layout
const W = 172, H = 64, INNER = 40, GAP = 44, LAYER = 150;

function computeLayout() {
  const g = state.graph, focus = state.focus;
  if (!focus || !state.people.has(focus)) return null;
  const parentsOf = new Map(), childrenOf = new Map(), partnersOf = new Map();
  const push = (m, k, v) => (m.get(k) || m.set(k, []).get(k)).push(v);
  for (const l of g.links) { push(parentsOf, l.child_id, l); push(childrenOf, l.parent_id, l); }
  for (const c of g.couples) { push(partnersOf, c.partner1_id, c.partner2_id); push(partnersOf, c.partner2_id, c.partner1_id); }

  // Generations by walking out from the focus person.
  const gen = new Map([[focus, 0]]), order = [focus], queue = [focus];
  while (queue.length) {
    const id = queue.shift(), gi = gen.get(id);
    const visit = (o, gj) => {
      if (gen.has(o) || gj < -state.up || gj > state.down) return;
      gen.set(o, gj); order.push(o); queue.push(o);
    };
    for (const p of partnersOf.get(id) || []) visit(p, gi);
    for (const l of parentsOf.get(id) || []) visit(l.parent_id, gi - 1);
    for (const l of childrenOf.get(id) || []) visit(l.child_id, gi + 1);
  }
  const rank = new Map(order.map((id, i) => [id, i]));

  // Units: partners in the same generation are kept side by side.
  const parent = new Map(order.map((id) => [id, id]));
  const find = (x) => (parent.get(x) === x ? x : (parent.set(x, find(parent.get(x))), parent.get(x)));
  for (const c of g.couples) {
    const a = c.partner1_id, b = c.partner2_id;
    if (gen.has(a) && gen.has(b) && gen.get(a) === gen.get(b)) parent.set(find(a), find(b));
  }
  const groups = new Map();
  for (const id of order) push(groups, find(id), id);
  const units = [];
  for (const members of groups.values()) units.push({ members: orderUnit(members, partnersOf), gen: gen.get(members[0]) });
  const unitOf = new Map();
  for (const u of units) for (const m of u.members) unitOf.set(m, u);

  const gens = [...new Set(units.map((u) => u.gen))].sort((a, b) => a - b);
  const layers = new Map(gens.map((gg) => [gg, units.filter((u) => u.gen === gg)
    .sort((a, b) => Math.min(...a.members.map((m) => rank.get(m))) - Math.min(...b.members.map((m) => rank.get(m))))]));

  const width = (u) => u.members.length * W + (u.members.length - 1) * INNER;
  const center = (id) => { const u = unitOf.get(id); return u.x + u.members.indexOf(id) * (W + INNER) + W / 2; };
  const placeSeq = (row) => { let x = 0; for (const u of row) { u.x = x; x += width(u) + GAP; } };
  for (const row of layers.values()) placeSeq(row);

  const related = (u, dir) => {
    const out = [];
    for (const m of u.members) {
      const ls = dir < 0 ? parentsOf.get(m) || [] : childrenOf.get(m) || [];
      for (const l of ls) {
        const o = dir < 0 ? l.parent_id : l.child_id;
        if (gen.has(o) && gen.get(o) === u.gen + dir) out.push(o);
      }
    }
    return out;
  };
  const avg = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;

  // Ordering: barycentre sweeps down and up.
  for (let it = 0; it < 6; it++) {
    for (const dir of [-1, 1]) {
      const seq = dir < 0 ? gens.slice(1) : gens.slice(0, -1).reverse();
      for (const gg of seq) {
        const row = layers.get(gg);
        const key = new Map(row.map((u) => {
          const r = related(u, dir);
          return [u, r.length ? avg(r.map(center)) : u.x + width(u) / 2];
        }));
        row.sort((a, b) => key.get(a) - key.get(b));
        placeSeq(row);
      }
    }
  }

  // Coordinates: pull units toward their relatives, keep order and spacing.
  for (let it = 0; it < 12; it++) {
    for (const gg of it % 2 ? [...gens].reverse() : gens) {
      const row = layers.get(gg);
      const want = row.map((u) => {
        const r = [...related(u, -1), ...related(u, 1)];
        return r.length ? avg(r.map(center)) - width(u) / 2 : u.x;
      });
      const L = want.slice(), R = want.slice();
      for (let i = 1; i < row.length; i++) L[i] = Math.max(L[i], L[i - 1] + width(row[i - 1]) + GAP);
      for (let i = row.length - 2; i >= 0; i--) R[i] = Math.min(R[i], R[i + 1] - width(row[i]) - GAP);
      row.forEach((u, i) => (u.x = (L[i] + R[i]) / 2));
    }
  }

  const minGen = gens[0];
  const nodes = new Map();
  for (const u of units) {
    u.members.forEach((id, i) => nodes.set(id, {
      id, p: state.people.get(id), gen: u.gen,
      x: u.x + i * (W + INNER), y: (u.gen - minGen) * LAYER, unit: u, idx: i,
    }));
  }
  return { nodes, parentsOf, gens };
}

function orderUnit(members, partnersOf) {
  if (members.length === 1) return members;
  const inUnit = new Set(members);
  const deg = (m) => (partnersOf.get(m) || []).filter((o) => inUnit.has(o)).length;
  // Walk the chain of partners from an end, so a person with two spouses sits between them.
  let start = members.find((m) => deg(m) <= 1) ?? members[0];
  if (members.length === 2) {
    const [a, b] = members;
    const pa = state.people.get(a), pb = state.people.get(b);
    start = pa.sex === "F" && pb.sex !== "F" ? b : a;
  }
  const out = [start], seen = new Set(out);
  while (out.length < members.length) {
    const last = out[out.length - 1];
    const next = (partnersOf.get(last) || []).find((o) => inUnit.has(o) && !seen.has(o))
      ?? members.find((m) => !seen.has(m));
    out.push(next); seen.add(next);
  }
  return out;
}

// ------------------------------------------------------------------ tree drawing
function svg(tag, attrs = {}, parent) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (parent) parent.appendChild(el);
  return el;
}

function renderTree() {
  const vp = $("#viewport");
  vp.innerHTML = "";
  const empty = state.graph.people.length === 0;
  $("#emptyState").hidden = !empty;
  $(".legend").hidden = empty;
  if (empty) return;
  const L = computeLayout();
  state.layout = L;
  if (!L) return;
  const { nodes } = L;

  const gEdges = svg("g", {}, vp), gUnions = svg("g", {}, vp), gNodes = svg("g", {}, vp);
  const couplesShown = state.graph.couples.filter((c) => nodes.has(c.partner1_id) && nodes.has(c.partner2_id));
  const coupleKey = (a, b) => (a < b ? `${a}-${b}` : `${b}-${a}`);
  const couplesByKey = new Map(couplesShown.map((c) => [coupleKey(c.partner1_id, c.partner2_id), c]));

  // Couples
  const unionPoint = new Map();
  for (const c of couplesShown) {
    const a = nodes.get(c.partner1_id), b = nodes.get(c.partner2_id);
    const ended = ["divorce", "annulment", "separation"].includes(c.end_reason);
    const cls = `u-line${ended ? " u-ended" : ""}${["marriage", "civil union"].includes(c.kind) ? "" : " u-partner"}`;
    const title = svg("title");
    title.textContent = `${c.kind}${c.start_date ? " " + c.start_date : ""}${c.end_reason ? ` — ended (${c.end_reason}) ${c.end_date}` : ""}`;
    if (a.unit === b.unit && Math.abs(a.idx - b.idx) === 1) {
      const [l, r] = a.x < b.x ? [a, b] : [b, a];
      const x1 = l.x + W, x2 = r.x, y = l.y + H / 2;
      const grp = svg("g", {}, gUnions);
      grp.appendChild(title);
      if (["marriage", "civil union"].includes(c.kind)) {
        svg("line", { x1, x2, y1: y - 2.5, y2: y - 2.5, class: cls }, grp);
        svg("line", { x1, x2, y1: y + 2.5, y2: y + 2.5, class: cls }, grp);
      } else {
        svg("line", { x1, x2, y1: y, y2: y, class: cls }, grp);
      }
      const mx = (x1 + x2) / 2;
      if (ended) svg("line", { x1: mx - 5, y1: y + 8, x2: mx + 5, y2: y - 8, class: "u-slash" }, grp);
      unionPoint.set(c.id, { x: mx, y });
    } else {
      const ax = a.x + W / 2, bx = b.x + W / 2;
      const top = Math.min(a.y, b.y) - 18;
      svg("path", { d: `M${ax},${a.y} C${ax},${top} ${bx},${top} ${bx},${b.y}`, class: cls + " u-partner" }, gUnions)
        .appendChild(title);
      unionPoint.set(c.id, { x: (ax + bx) / 2, y: Math.max(a.y, b.y) + H });
    }
  }

  // Parent → child lines
  const lanes = new Map();
  const laneFor = (gen, key) => {
    const m = lanes.get(gen) || lanes.set(gen, new Map()).get(gen);
    if (!m.has(key)) m.set(key, m.size);
    return m.get(key);
  };
  for (const child of nodes.values()) {
    const links = (L.parentsOf.get(child.id) || []).filter((l) => nodes.has(l.parent_id));
    const used = new Set(), sources = [];
    for (let i = 0; i < links.length; i++) {
      for (let j = i + 1; j < links.length; j++) {
        const a = links[i], b = links[j];
        if (used.has(a) || used.has(b) || a.kind !== b.kind) continue;
        const c = couplesByKey.get(coupleKey(a.parent_id, b.parent_id));
        if (c && unionPoint.has(c.id)) {
          used.add(a); used.add(b);
          sources.push({ key: `c${c.id}`, pt: unionPoint.get(c.id), kind: a.kind, gen: nodes.get(a.parent_id).gen });
        }
      }
    }
    for (const l of links) {
      if (used.has(l)) continue;
      const pn = nodes.get(l.parent_id);
      sources.push({ key: `p${pn.id}`, pt: { x: pn.x + W / 2, y: pn.y + H }, kind: l.kind, gen: pn.gen });
    }
    for (const s of sources) {
      const cx = child.x + W / 2, top = child.y;
      let d;
      if (s.gen === child.gen - 1) {
        const bus = top - 26 - (laneFor(child.gen, s.key + s.kind) % 4) * 7;
        d = `M${s.pt.x},${s.pt.y} V${bus} H${cx} V${top}`;
      } else {
        const mid = (s.pt.y + top) / 2;
        d = `M${s.pt.x},${s.pt.y} C${s.pt.x},${mid + 60} ${cx},${top - 60} ${cx},${top}`;
      }
      const path = svg("path", { d, class: `edge l-${s.kind}` }, gEdges);
      const t = svg("title", {}, path);
      t.textContent = `${KIND_LABEL[s.kind]} — ${child.p.display_name}`;
    }
  }

  // People
  for (const n of nodes.values()) drawNode(gNodes, n);

  if (state.fitNext && $("#tree").clientWidth > 0) { fitView(); state.fitNext = false; }
  applyView();
}

function drawNode(parent, n) {
  const p = n.p;
  const g = svg("g", {
    class: `node ${p.sex}${p.deceased ? " deceased" : ""}${p.id === state.focus ? " focus" : ""}${p.id === state.selected ? " selected" : ""}`,
    transform: `translate(${n.x},${n.y})`, "data-id": p.id, tabindex: 0,
  }, parent);
  svg("rect", { class: "box", width: W, height: H, rx: 9 }, g);
  svg("rect", { class: "bar", x: 0, y: 8, width: 4, height: H - 16, rx: 2 }, g);
  let tx = 14;
  if (p.portrait_id) {
    const id = `clip${p.id}`;
    const cp = svg("clipPath", { id }, g);
    svg("circle", { cx: 34, cy: H / 2, r: 21 }, cp);
    svg("circle", { class: "portrait-ring", cx: 34, cy: H / 2, r: 22 }, g);
    svg("image", { href: `/photo/${p.portrait_id}`, x: 12, y: H / 2 - 22, width: 44, height: 44,
      "clip-path": `url(#${id})`, preserveAspectRatio: "xMidYMid slice" }, g);
    tx = 62;
  }
  const maxChars = Math.floor((W - tx - 8) / 7.1);
  const fit = (s) => (s.length > maxChars ? s.slice(0, maxChars - 1) + "…" : s);
  const name = svg("text", { class: "name", x: tx, y: 24 }, g);
  name.textContent = fit(p.display_name);
  const sub1 = svg("text", { class: "sub", x: tx, y: 41 }, g);
  sub1.textContent = lifespan(p);
  if (p.nee) {
    const sub2 = svg("text", { class: "sub", x: tx, y: 55 }, g);
    sub2.textContent = fit(`${nee(p)} ${p.nee}`);
  }
  const t = svg("title", {}, g);
  t.textContent = `${p.display_name}${p.nee ? ` (${nee(p)} ${p.nee})` : ""}\nClick for details · double-click to centre the tree here`;
}

// ------------------------------------------------------------------ pan & zoom
function applyView() {
  const { x, y, k } = state.view;
  $("#viewport").setAttribute("transform", `translate(${x},${y}) scale(${k})`);
}

function bounds() {
  const L = state.layout;
  if (!L || !L.nodes.size) return null;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const n of L.nodes.values()) {
    x0 = Math.min(x0, n.x); y0 = Math.min(y0, n.y);
    x1 = Math.max(x1, n.x + W); y1 = Math.max(y1, n.y + H);
  }
  return { x0, y0: y0 - 30, x1, y1 };
}

function fitView() {
  const b = bounds();
  if (!b) return;
  const svgEl = $("#tree");
  const w = svgEl.clientWidth, h = svgEl.clientHeight - 50;
  const panelW = state.selected && !$("#panel").hidden ? Math.min(400, w * 0.5) : 0;
  const availW = w - panelW;
  const k = Math.max(0.25, Math.min(1.1, Math.min((availW - 40) / (b.x1 - b.x0), (h - 40) / (b.y1 - b.y0))));
  state.view = { k, x: (availW - (b.x1 - b.x0) * k) / 2 - b.x0 * k, y: (h - (b.y1 - b.y0) * k) / 2 - b.y0 * k + 10 };
  applyView();
}

function zoomAt(factor, cx, cy) {
  const v = state.view;
  const k = Math.max(0.2, Math.min(2.5, v.k * factor));
  v.x = cx - ((cx - v.x) * k) / v.k;
  v.y = cy - ((cy - v.y) * k) / v.k;
  v.k = k;
  applyView();
}

function setupPanZoom() {
  const el = $("#tree");
  let drag = null, moved = false;
  const pointers = new Map();
  let pinch = null;
  el.addEventListener("wheel", (e) => {
    e.preventDefault();
    const r = el.getBoundingClientRect();
    zoomAt(Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top);
  }, { passive: false });
  el.addEventListener("pointerdown", (e) => {
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      pinch = { d: Math.hypot(a.x - b.x, a.y - b.y) };
      drag = null;
      return;
    }
    drag = { x: e.clientX, y: e.clientY, vx: state.view.x, vy: state.view.y };
    moved = false;
  });
  el.addEventListener("pointermove", (e) => {
    if (pointers.has(e.pointerId)) pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pinch && pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      const r = el.getBoundingClientRect();
      zoomAt(d / pinch.d, (a.x + b.x) / 2 - r.left, (a.y + b.y) / 2 - r.top);
      pinch.d = d;
      moved = true;
      return;
    }
    if (!drag) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (!moved && Math.hypot(dx, dy) > 4) { moved = true; el.classList.add("dragging"); el.setPointerCapture(e.pointerId); }
    if (moved) {
      state.view.x = drag.vx + dx;
      state.view.y = drag.vy + dy;
      applyView();
    }
  });
  const end = (e) => {
    pointers.delete(e.pointerId);
    if (pointers.size < 2) pinch = null;
    drag = null;
    el.classList.remove("dragging");
  };
  el.addEventListener("pointerup", end);
  el.addEventListener("pointercancel", end);
  el.addEventListener("click", (e) => {
    if (moved) { moved = false; return; }
    const node = e.target.closest(".node");
    if (node) openPanel(Number(node.dataset.id));
  });
  el.addEventListener("dblclick", (e) => {
    const node = e.target.closest(".node");
    if (node) setFocus(Number(node.dataset.id));
  });
  el.addEventListener("keydown", (e) => {
    const node = e.target.closest && e.target.closest(".node");
    if (node && e.key === "Enter") openPanel(Number(node.dataset.id));
  });
  $("#zoomIn").onclick = () => zoomAt(1.25, el.clientWidth / 2, el.clientHeight / 2);
  $("#zoomOut").onclick = () => zoomAt(0.8, el.clientWidth / 2, el.clientHeight / 2);
  $("#zoomFit").onclick = fitView;
}

// ------------------------------------------------------------------ side panel
async function openPanel(id, quiet = false) {
  state.selected = id;
  $$(".node").forEach((n) => n.classList.toggle("selected", Number(n.dataset.id) === id));
  let p;
  try { p = await api("GET", `/api/people/${id}`); } catch (e) { if (!quiet) toast(e.message); return; }
  const panel = $("#panel");
  const rel = (link, extra = "") => `
    <div class="rel">
      <div class="who"><button class="link" data-goto="${link.person.id}">${esc(link.person.display_name)}</button>
        <small>${esc(lifespan(link.person))}${link.date ? ` · ${esc(link.date)}` : ""}</small></div>
      <span class="badge ${link.kind}">${KIND_LABEL[link.kind]}</span>
      ${extra}
    </div>`;
  const siblings = computeSiblings(id);
  const coupleLine = (c) => {
    const bits = [];
    const verb = { marriage: "Married", "civil union": "Civil union", partnership: "Partners", engagement: "Engaged", other: "Together" }[c.kind];
    bits.push(verb + (c.start_date ? ` ${c.start_date}` : "") + (c.start_place ? `, ${c.start_place}` : ""));
    if (c.end_reason || c.end_date) {
      const why = { divorce: "Divorced", death: "Until death", annulment: "Annulled", separation: "Separated", other: "Ended", "": "Ended" }[c.end_reason];
      bits.push(why + (c.end_date ? ` ${c.end_date}` : ""));
    }
    return bits.join(" · ");
  };
  panel.innerHTML = `
    <button class="ghost icon close" data-act="close" title="Close">✕</button>
    ${p.portrait_id ? `<img class="portrait" src="/photo/${p.portrait_id}" alt="">` : ""}
    <h2>${esc(p.display_name)}</h2>
    ${p.nee ? `<div class="nee">${nee(p)} ${esc(p.given_names)} ${esc(p.nee)}</div>` : ""}
    <div class="vital"><b>Born</b> ${esc(p.birth_date || "—")}${p.birth_place ? `, ${esc(p.birth_place)}` : ""}</div>
    ${p.deceased ? `<div class="vital"><b>Died</b> ${esc(p.death_date || "—")}${p.death_place ? `, ${esc(p.death_place)}` : ""}</div>` : ""}
    <div class="actions">
      <button data-act="edit">Edit details</button>
      ${p.id !== state.focus ? `<button class="ghost" data-act="focus">Centre tree here</button>` : ""}
      <button class="ghost" data-act="kin">How are we related?</button>
    </div>

    <h3>Parents</h3>
    ${p.parents.map((l) => rel(l, `<button class="ghost icon" data-link="${l.id}" title="Change">✎</button>`)).join("") || `<p class="muted">None recorded.</p>`}
    <button class="ghost" data-add="parent">＋ Add parent</button>

    <h3>Partners</h3>
    ${p.couples.map((c) => `
      <div class="rel">
        <div class="who"><button class="link" data-goto="${c.partner.id}">${esc(c.partner.display_name)}</button>
          <small>${esc(coupleLine(c))}</small></div>
        <button class="ghost icon" data-couple="${c.id}" title="Change">✎</button>
      </div>`).join("") || `<p class="muted">None recorded.</p>`}
    <button class="ghost" data-add="partner">＋ Add partner or spouse</button>

    <h3>Children</h3>
    ${p.children.map((l) => rel(l, `<button class="ghost icon" data-link="${l.id}" title="Change">✎</button>`)).join("") || `<p class="muted">None recorded.</p>`}
    <button class="ghost" data-add="child">＋ Add child</button>

    ${siblings.length ? `<h3>Siblings</h3>${siblings.map((s) => `
      <div class="rel"><div class="who"><button class="link" data-goto="${s.p.id}">${esc(s.p.display_name)}</button>
        <small>${esc(lifespan(s.p))}</small></div>${s.tag ? `<span class="badge">${s.tag}</span>` : ""}</div>`).join("")}` : ""}

    ${p.alt_names.length ? `<h3>Other names</h3>${p.alt_names.map((n) => `<div class="vital"><b>${esc(cap(n.kind))}:</b> ${esc([n.given_names, n.surname].filter(Boolean).join(" "))}${n.from_date ? ` <span class="muted">(from ${esc(n.from_date)})</span>` : ""}</div>`).join("")}` : ""}

    ${p.facts.length ? `<h3>Life events &amp; details</h3>${p.facts.map((f) => `<div class="vital"><b>${esc(cap(f.kind))}</b> ${esc([f.detail, f.date, f.place].filter(Boolean).join(" · "))}</div>`).join("")}` : ""}

    ${p.notes ? `<h3>Notes</h3><div class="notes">${esc(p.notes)}</div>` : ""}

    <h3>Stories</h3>
    ${p.stories.map((s) => `<div class="rel"><div class="who"><button class="link" data-story="${s.id}">${esc(s.title || "Untitled")}</button><small>${esc(s.date)}</small></div></div>`).join("") || `<p class="muted">No stories yet.</p>`}
    <button class="ghost" data-act="story">＋ Write a story about ${esc(p.given_names || "them")}</button>

    <h3>Photos</h3>
    <div class="thumbs">${p.media.map((m) => `<img src="/photo/${m.id}" data-photo="${m.id}" alt="${esc(m.caption)}" title="${esc(m.caption)}">`).join("")}</div>
    <label class="button ghost" style="margin-top:8px;background:transparent;color:var(--accent)">＋ Add photos<input type="file" accept="image/*" multiple hidden data-act="upload"></label>
  `;
  const wasHidden = panel.hidden;
  panel.hidden = false;
  keepVisible(id, wasHidden);
  panel.onclick = async (e) => {
    const t = e.target.closest("button, img");
    if (!t) return;
    if (t.dataset.goto) return openPanel(Number(t.dataset.goto));
    if (t.dataset.add) return relationModal(p, t.dataset.add);
    if (t.dataset.link) return linkModal(Number(t.dataset.link), p);
    if (t.dataset.couple) return coupleModal(p.couples.find((c) => c.id === Number(t.dataset.couple)));
    if (t.dataset.story) return storyModal(Number(t.dataset.story));
    if (t.dataset.photo) return lightbox(p.media.find((m) => m.id === Number(t.dataset.photo)), p);
    const act = t.dataset.act;
    if (act === "close") closePanel();
    if (act === "edit") personModal(p);
    if (act === "focus") setFocus(p.id);
    if (act === "story") storyModal(null, [p.id]);
    if (act === "kin") { switchTab("kin"); kinA.set(state.focus !== p.id ? state.focus : null); kinB.set(p.id); runKin(); }
  };
  $("input[data-act=upload]", panel).onchange = async (e) => {
    await uploadFiles(e.target.files, [p.id]);
    openPanel(p.id, true);
  };
}

// Slide the tree so the selected person isn't hidden behind the side panel.
function keepVisible(id) {
  const n = state.layout && state.layout.nodes.get(id);
  const svgEl = $("#tree");
  if (!n || !svgEl.clientWidth) return;
  const { k } = state.view;
  const avail = svgEl.clientWidth - $("#panel").offsetWidth;
  const left = n.x * k + state.view.x, right = left + W * k;
  if (right > avail - 16 || left < 16) {
    state.view.x += (avail / 2) - (left + right) / 2;
    applyView();
  }
}

function closePanel() {
  state.selected = null;
  $("#panel").hidden = true;
  $$(".node.selected").forEach((n) => n.classList.remove("selected"));
}

function cap(s) { return s ? s[0].toUpperCase() + s.slice(1) : s; }

function computeSiblings(id) {
  const links = state.graph.links;
  const myParents = links.filter((l) => l.child_id === id);
  const mySet = new Set(myParents.map((l) => l.parent_id));
  const byId = new Map();
  for (const l of myParents) {
    for (const o of links) {
      if (o.parent_id === l.parent_id && o.child_id !== id) {
        const e = byId.get(o.child_id) || byId.set(o.child_id, { shared: new Set(), kinds: new Set() }).get(o.child_id);
        e.shared.add(o.parent_id);
        e.kinds.add(l.kind); e.kinds.add(o.kind);
      }
    }
  }
  const out = [];
  for (const [sid, e] of byId) {
    const theirs = new Set(links.filter((l) => l.child_id === sid).map((l) => l.parent_id));
    const same = theirs.size === mySet.size && [...theirs].every((x) => mySet.has(x));
    let tag = same ? "" : "half";
    if (e.kinds.has("adoptive")) tag = "by adoption";
    if (e.kinds.has("step") && !e.kinds.has("biological")) tag = "step";
    if (e.kinds.has("foster")) tag = "foster";
    out.push({ p: state.people.get(sid), tag });
  }
  return out.sort((a, b) => (a.p.birth_year || 9999) - (b.p.birth_year || 9999));
}

// ------------------------------------------------------------------ modal helpers
function openModal(html, { onSubmit, onReady, wide } = {}) {
  const dlg = $("#modal"), form = $("#modalForm");
  dlg.classList.toggle("lightbox", !!wide);
  form.innerHTML = html + `<p class="error" hidden></p>`;
  form.onsubmit = async (e) => {
    e.preventDefault();
    const btn = e.submitter;
    if (btn && btn.value === "cancel") return dlg.close();
    if (!onSubmit) return dlg.close();
    const err = $(".error", form);
    err.hidden = true;
    try {
      const result = await onSubmit(new FormData(form), btn ? btn.value : "");
      if (result !== false) dlg.close();
    } catch (ex) {
      err.textContent = ex.message;
      err.hidden = false;
    }
  };
  // Enter in a text box should save, never trigger "Delete" (the first button).
  form.onkeydown = (e) => {
    if (e.key !== "Enter" || e.defaultPrevented || e.target.tagName !== "INPUT" || e.target.type === "checkbox") return;
    e.preventDefault();
    const save = $("button[value=save]", form);
    if (save) form.requestSubmit(save);
  };
  if (onReady) onReady(form);
  dlg.showModal();
  const first = $("input:not([type=hidden]):not([type=checkbox]), textarea", form);
  if (first) first.focus();
}

function field(name, lab, value = "", { type = "text", full = false, placeholder = "" } = {}) {
  return `<label class="field${full ? " full" : ""}"><span>${esc(lab)}</span>
    <input name="${name}" type="${type}" value="${esc(value)}" placeholder="${esc(placeholder)}"></label>`;
}
function select(name, lab, options, value, { full = false } = {}) {
  return `<label class="field${full ? " full" : ""}"><span>${esc(lab)}</span><select name="${name}">${options.map(([v, t]) =>
    `<option value="${esc(v)}"${v === value ? " selected" : ""}>${esc(t)}</option>`).join("")}</select></label>`;
}
const DATE_HINT = "e.g. 5 Mar 1923, abt 1900, 1890s";
const sexOptions = Object.entries(SEX_LABEL);
const kindOptions = () => state.meta.kinds.parent.map((k) => [k, KIND_HELP[k]]);
const coupleKindOptions = () => state.meta.kinds.couple.map((k) => [k, cap(k)]);
const endOptions = () => state.meta.kinds.end.map((k) => [k, k ? cap(k) : "Still together / not ended"]);

// ------------------------------------------------------------------ person form
function personModal(p = null) {
  const isNew = !p;
  p = p || { given_names: "", birth_surname: "", sex: "U", alt_names: [], facts: [], deceased: false };
  const nameRow = (n = {}) => `<div class="item">
      <select data-k="kind">${state.meta.kinds.name.map((k) => `<option value="${k}"${k === (n.kind || "married") ? " selected" : ""}>${cap(k)}</option>`).join("")}</select>
      <input data-k="surname" placeholder="Surname" value="${esc(n.surname || "")}">
      <input data-k="from_date" placeholder="From (date)" value="${esc(n.from_date || "")}">
      <button type="button" class="ghost icon" data-remove title="Remove">✕</button></div>`;
  const factRow = (f = {}) => `<div class="item fact">
      <select data-k="kind">${state.meta.kinds.fact.map((k) => `<option value="${k}"${k === (f.kind || "occupation") ? " selected" : ""}>${cap(k)}</option>`).join("")}</select>
      <input data-k="date" placeholder="Date" value="${esc(f.date || "")}">
      <input data-k="place" placeholder="Place" value="${esc(f.place || "")}">
      <input data-k="detail" placeholder="Detail" value="${esc(f.detail || "")}">
      <button type="button" class="ghost icon" data-remove title="Remove">✕</button></div>`;
  openModal(`
    <h2>${isNew ? "Add a person" : `Edit ${esc(p.display_name)}`}</h2>
    <div class="grid2">
      ${field("given_names", "Given names", p.given_names)}
      ${field("birth_surname", "Surname at birth (maiden name)", p.birth_surname)}
      ${select("sex", "Sex", sexOptions, p.sex)}
      <span></span>
      ${field("birth_date", "Born (date)", p.birth_date, { placeholder: DATE_HINT })}
      ${field("birth_place", "Born (place)", p.birth_place)}
      <label class="check field full"><input type="checkbox" name="deceased"${p.deceased ? " checked" : ""}> Has died</label>
      <div class="grid2 full death"${p.deceased ? "" : " hidden"}>
        ${field("death_date", "Died (date)", p.death_date, { placeholder: DATE_HINT })}
        ${field("death_place", "Died (place)", p.death_place)}
      </div>
    </div>
    <div class="field"><span>Later names — marriage, adoption, legal change, nicknames</span>
      <div class="repeat" id="altNames">${p.alt_names.map(nameRow).join("")}</div>
      <div><button type="button" class="ghost" data-addrow="alt">＋ Add a name</button></div></div>
    <div class="field"><span>Life events &amp; details — occupation, residence, military service, immigration…</span>
      <div class="repeat" id="facts">${p.facts.map(factRow).join("")}</div>
      <div><button type="button" class="ghost" data-addrow="fact">＋ Add an event</button></div></div>
    <label class="field"><span>Notes</span><textarea name="notes" rows="4">${esc(p.notes || "")}</textarea></label>
    <div class="modal-actions">
      ${isNew ? "" : `<button type="submit" value="delete" class="danger left">Delete person</button>`}
      <button type="submit" value="cancel" class="ghost" formnovalidate>Cancel</button>
      <button type="submit" value="save">${isNew ? "Add" : "Save"}</button>
    </div>`, {
    onReady(form) {
      const deceased = $("input[name=deceased]", form);
      deceased.onchange = () => ($(".death", form).hidden = !deceased.checked);
      form.addEventListener("click", (e) => {
        const add = e.target.closest("[data-addrow]");
        if (add) {
          const box = add.dataset.addrow === "alt" ? $("#altNames", form) : $("#facts", form);
          box.insertAdjacentHTML("beforeend", add.dataset.addrow === "alt" ? nameRow() : factRow());
          $("input", box.lastElementChild).focus();
        }
        const rm = e.target.closest("[data-remove]");
        if (rm) rm.closest(".item").remove();
      });
    },
    async onSubmit(fd, action) {
      if (action === "delete") {
        if (!confirm(`Delete ${p.display_name}? Their links, and their place in any stories and photos, will be removed. This can't be undone.`)) return false;
        await api("DELETE", `/api/people/${p.id}`);
        closePanel();
        toast("Deleted.");
        return refresh();
      }
      const rows = (sel) => $$(`${sel} .item`).map((it) =>
        Object.fromEntries($$("[data-k]", it).map((i) => [i.dataset.k, i.value])));
      const body = {
        given_names: fd.get("given_names"), birth_surname: fd.get("birth_surname"), sex: fd.get("sex"),
        birth_date: fd.get("birth_date"), birth_place: fd.get("birth_place"),
        deceased: fd.get("deceased") === "on", death_date: fd.get("death_date") || "",
        death_place: fd.get("death_place") || "", notes: fd.get("notes"),
        alt_names: rows("#altNames"), facts: rows("#facts"),
      };
      if (!body.deceased) { body.death_date = ""; body.death_place = ""; }
      if (!body.given_names.trim() && !body.birth_surname.trim()) throw new Error("Please enter at least a name.");
      const saved = isNew ? await api("POST", "/api/people", body) : await api("PUT", `/api/people/${p.id}`, body);
      if (isNew && !state.focus) state.focus = saved.id;
      await refresh();
      openPanel(saved.id, true);
    },
  });
}

// ------------------------------------------------------------------ add relation
function relationModal(p, role) {
  const who = esc(p.display_name);
  const title = { parent: `Add a parent of ${who}`, child: `Add a child of ${who}`, partner: `Add a partner or spouse of ${who}` }[role];
  const currentPartners = p.couples.filter((c) => !["divorce", "annulment", "separation"].includes(c.end_reason));
  const parentsWithoutPartner = p.parents;
  let mode = "new";
  let existing;
  const kindBlock = role === "partner" ? `
      <div class="grid2">
        ${select("ckind", "Relationship", coupleKindOptions(), "marriage")}
        <span></span>
        ${field("start_date", "Start date (e.g. wedding)", "", { placeholder: DATE_HINT })}
        ${field("start_place", "Place", "")}
        ${select("end_reason", "Ended?", endOptions(), "")}
        ${field("end_date", "End date", "")}
      </div>` : `
      <div class="grid2">
        ${select("kind", role === "parent" ? "This parent is a…" : "Kind of parent", kindOptions(), "biological", { full: true })}
        ${field("date", "Date (e.g. of adoption or marriage)", "", { placeholder: "optional" })}
        ${field("notes", "Note", "", { placeholder: "optional" })}
      </div>`;
  const alsoBlock = role === "child" && currentPartners.length ? `
      <div class="field"><span>Also a parent of this child</span>
        ${currentPartners.map((c, i) => `<label class="check"><input type="checkbox" name="also" value="${c.partner.id}"${currentPartners.length === 1 ? " checked" : ""}> ${esc(c.partner.display_name)} <span class="muted">(same kind as above)</span></label>`).join("")}
      </div>` : role === "parent" && parentsWithoutPartner.length ? `
      <div class="field"><span>Also record a marriage with…</span>
        ${parentsWithoutPartner.map((l) => `<label class="check"><input type="checkbox" name="marry" value="${l.person.id}"> ${esc(l.person.display_name)}</label>`).join("")}
      </div>` : "";
  openModal(`
    <h2>${title}</h2>
    <div class="seg" role="tablist">
      <button type="button" data-mode="new" class="on">Someone new</button>
      <button type="button" data-mode="existing">Someone already in the tree</button>
    </div>
    <div class="mode-new grid2">
      ${field("given_names", "Given names", "")}
      ${field("birth_surname", "Surname at birth", role === "child" ? p.surname : "")}
      ${select("sex", "Sex", sexOptions, "U")}
      ${field("birth_date", "Born", "", { placeholder: DATE_HINT })}
    </div>
    <div class="mode-existing" hidden><span class="picker-slot" id="relPicker"></span>
      <p class="hint">Use this to connect people already in the tree — for example, a cousin who was later adopted by an aunt.</p></div>
    ${kindBlock}
    ${alsoBlock}
    <div class="modal-actions">
      <button type="submit" value="cancel" class="ghost" formnovalidate>Cancel</button>
      <button type="submit" value="save">Add</button>
    </div>`, {
    onReady(form) {
      existing = makePicker({ exclude: (x) => x.id === p.id });
      $("#relPicker", form).appendChild(existing.el);
      $$(".seg button", form).forEach((b) => b.onclick = () => {
        mode = b.dataset.mode;
        $$(".seg button", form).forEach((x) => x.classList.toggle("on", x === b));
        $(".mode-new", form).hidden = mode !== "new";
        $(".mode-existing", form).hidden = mode !== "existing";
        (mode === "new" ? $("input[name=given_names]", form) : existing).focus();
      });
    },
    async onSubmit(fd) {
      let otherId;
      if (mode === "existing") {
        otherId = existing.value;
        if (!otherId) throw new Error("Pick someone from the list.");
      } else {
        if (!fd.get("given_names").trim() && !fd.get("birth_surname").trim()) throw new Error("Please enter a name.");
        const created = await api("POST", "/api/people", {
          given_names: fd.get("given_names"), birth_surname: fd.get("birth_surname"),
          sex: fd.get("sex"), birth_date: fd.get("birth_date"),
        });
        otherId = created.id;
      }
      try {
        if (role === "partner") {
          await api("POST", "/api/couples", {
            partner1_id: p.id, partner2_id: otherId, kind: fd.get("ckind"),
            start_date: fd.get("start_date"), start_place: fd.get("start_place"),
            end_reason: fd.get("end_reason"), end_date: fd.get("end_date"),
          });
        } else {
          const kind = fd.get("kind");
          const [child, parent] = role === "parent" ? [p.id, otherId] : [otherId, p.id];
          await api("POST", "/api/links", { child_id: child, parent_id: parent, kind, date: fd.get("date"), notes: fd.get("notes") });
          for (const also of fd.getAll("also")) {
            await api("POST", "/api/links", { child_id: otherId, parent_id: Number(also), kind, date: fd.get("date") });
          }
          for (const m of fd.getAll("marry")) {
            await api("POST", "/api/couples", { partner1_id: Number(m), partner2_id: otherId, kind: "marriage" });
          }
        }
      } catch (e) {
        if (mode === "new") await api("DELETE", `/api/people/${otherId}`).catch(() => {});
        throw e;
      }
      await refresh();
      openPanel(p.id, true);
    },
  });
}

function linkModal(linkId, contextPerson) {
  const l = [...contextPerson.parents, ...contextPerson.children].find((x) => x.id === linkId);
  const parentName = l.parent_id === contextPerson.id ? contextPerson.display_name : l.person.display_name;
  const childName = l.child_id === contextPerson.id ? contextPerson.display_name : l.person.display_name;
  openModal(`
    <h2>${esc(parentName)} → ${esc(childName)}</h2>
    <p class="hint">${esc(parentName)} is a parent of ${esc(childName)}.</p>
    <div class="grid2">
      ${select("kind", "Kind of parent", kindOptions(), l.kind, { full: true })}
      ${field("date", "Date", l.date)}
      ${field("notes", "Note", l.notes)}
    </div>
    <div class="modal-actions">
      <button type="submit" value="delete" class="danger left">Remove this link</button>
      <button type="submit" value="cancel" class="ghost">Cancel</button>
      <button type="submit" value="save">Save</button>
    </div>`, {
    async onSubmit(fd, action) {
      if (action === "delete") {
        if (!confirm("Remove this parent–child link? The people themselves stay in the tree.")) return false;
        await api("DELETE", `/api/links/${l.id}`);
      } else {
        await api("PUT", `/api/links/${l.id}`, { kind: fd.get("kind"), date: fd.get("date"), notes: fd.get("notes") });
      }
      await refresh();
      openPanel(contextPerson.id, true);
    },
  });
}

function coupleModal(c) {
  openModal(`
    <h2>${esc(c.partner.display_name)}</h2>
    <div class="grid2">
      ${select("kind", "Relationship", coupleKindOptions(), c.kind)}
      <span></span>
      ${field("start_date", "Start date", c.start_date, { placeholder: DATE_HINT })}
      ${field("start_place", "Place", c.start_place)}
      ${select("end_reason", "Ended?", endOptions(), c.end_reason)}
      ${field("end_date", "End date", c.end_date)}
    </div>
    <label class="field"><span>Notes</span><textarea name="notes" rows="3">${esc(c.notes)}</textarea></label>
    <div class="modal-actions">
      <button type="submit" value="delete" class="danger left">Remove this relationship</button>
      <button type="submit" value="cancel" class="ghost">Cancel</button>
      <button type="submit" value="save">Save</button>
    </div>`, {
    async onSubmit(fd, action) {
      if (action === "delete") {
        if (!confirm("Remove this marriage/partnership record? Both people stay in the tree.")) return false;
        await api("DELETE", `/api/couples/${c.id}`);
      } else {
        await api("PUT", `/api/couples/${c.id}`, Object.fromEntries(
          ["kind", "start_date", "start_place", "end_reason", "end_date", "notes"].map((k) => [k, fd.get(k)])));
      }
      await refresh();
    },
  });
}

// ------------------------------------------------------------------ people list
function renderPeople() {
  const q = $("#peopleSearch").value.trim().toLowerCase();
  const rows = [...state.graph.people].sort((a, b) =>
    a.surname.localeCompare(b.surname) || a.given_names.localeCompare(b.given_names))
    .filter((p) => !q || [p.display_name, p.nee, p.birth_surname, p.birth_date, p.birth_place, p.death_date, p.death_place,
      ...p.alt_names.map((n) => n.surname)].join(" ").toLowerCase().includes(q));
  $("#peopleBody").innerHTML = rows.map((p) => `
    <tr data-id="${p.id}">
      <td><b>${esc(p.display_name)}</b>${p.nee ? ` <span class="muted">${nee(p)} ${esc(p.nee)}</span>` : ""}</td>
      <td>${esc([p.birth_date, p.birth_place].filter(Boolean).join(", "))}</td>
      <td>${esc([p.death_date, p.death_place].filter(Boolean).join(", ")) || (p.deceased ? "deceased" : "")}</td>
      <td class="muted">${p.id === state.focus ? "centre of tree" : ""}</td>
    </tr>`).join("") || `<tr><td colspan="4" class="muted">No one yet.</td></tr>`;
}

// ------------------------------------------------------------------ stories
let storiesCache = [];
async function renderStories() {
  storiesCache = await api("GET", "/api/stories");
  const q = $("#storySearch").value.trim().toLowerCase();
  const list = storiesCache.filter((s) => !q || `${s.title} ${s.body} ${s.told_by}`.toLowerCase().includes(q));
  $("#storyList").innerHTML = list.map((s) => `
    <article class="story">
      <h3>${esc(s.title || "Untitled")}</h3>
      <div class="meta">${esc([s.date, s.told_by && `told by ${s.told_by}`].filter(Boolean).join(" · "))}</div>
      <div class="body">${esc(s.body)}</div>
      <div class="chips">${s.person_ids.map((id) => state.people.get(id)).filter(Boolean)
        .map((p) => `<button class="chip" data-goto="${p.id}">${esc(p.display_name)}</button>`).join("")}
        <span class="spacer"></span><button class="ghost" data-edit="${s.id}">Edit</button></div>
    </article>`).join("") || `<p class="muted">No stories yet. Family stories — how people met, where they came from, the funny and the hard times — are often the most treasured part of a family history.</p>`;
}

async function storyModal(id, presetPeople = []) {
  const s = id ? await api("GET", `/api/stories/${id}`) : { title: "", body: "", date: "", told_by: "", person_ids: presetPeople };
  let people;
  openModal(`
    <h2>${id ? "Edit story" : "Write a story"}</h2>
    ${field("title", "Title", s.title)}
    <div class="grid2">
      ${field("date", "When it happened", s.date, { placeholder: "e.g. Summer 1952" })}
      ${field("told_by", "Told by", s.told_by, { placeholder: "Who shared it" })}
    </div>
    <div class="field"><span>Who it's about</span><div id="storyPeople"></div></div>
    <label class="field"><span>The story</span><textarea name="body" rows="12">${esc(s.body)}</textarea></label>
    <div class="modal-actions">
      ${id ? `<button type="submit" value="delete" class="danger left">Delete story</button>` : ""}
      <button type="submit" value="cancel" class="ghost">Cancel</button>
      <button type="submit" value="save">Save</button>
    </div>`, {
    onReady(form) { people = makeMultiPicker(s.person_ids); $("#storyPeople", form).appendChild(people.el); },
    async onSubmit(fd, action) {
      if (action === "delete") {
        if (!confirm("Delete this story? This can't be undone.")) return false;
        await api("DELETE", `/api/stories/${id}`);
      } else {
        const body = { title: fd.get("title"), date: fd.get("date"), told_by: fd.get("told_by"), body: fd.get("body"), person_ids: people.value };
        if (!body.title.trim() && !body.body.trim()) throw new Error("Give the story a title or some text.");
        await (id ? api("PUT", `/api/stories/${id}`, body) : api("POST", "/api/stories", body));
      }
      if ($("#tab-stories").classList.contains("active")) renderStories();
      if (state.selected) openPanel(state.selected, true);
    },
  });
}

// ------------------------------------------------------------------ photos
async function uploadFiles(files, personIds = []) {
  let n = 0;
  for (const f of files) {
    const data = await new Promise((res, rej) => {
      const r = new FileReader();
      r.onload = () => res(r.result);
      r.onerror = rej;
      r.readAsDataURL(f);
    });
    try {
      await api("POST", "/api/media", { data, mime: f.type || "image/jpeg", name: f.name, person_ids: personIds });
      n++;
    } catch (e) { toast(`${f.name}: ${e.message}`); }
  }
  if (n) toast(`${n} photo${n > 1 ? "s" : ""} added.`);
}

let mediaCache = [];
async function renderPhotos() {
  mediaCache = await api("GET", "/api/media");
  $("#photoGrid").innerHTML = mediaCache.map((m) => `
    <figure class="photo" style="margin:0">
      <img src="/photo/${m.id}" alt="${esc(m.caption)}" data-view="${m.id}" loading="lazy">
      <figcaption class="cap">
        ${m.caption ? esc(m.caption) : `<span class="muted">${esc(m.original_name || "No caption")}</span>`}
        ${m.date ? `<span class="muted"> · ${esc(m.date)}</span>` : ""}
        <div class="chips">${m.person_ids.map((id) => state.people.get(id)).filter(Boolean)
          .map((p) => `<button class="chip" data-goto="${p.id}">${esc(p.display_name)}</button>`).join("")}
          <span class="spacer"></span><button class="link" data-edit="${m.id}">Edit</button></div>
      </figcaption>
    </figure>`).join("") || `<p class="muted">No photos yet. Add scans of old prints, documents, gravestones, letters…</p>`;
}

function photoModal(m) {
  let people;
  openModal(`
    <h2>Photo details</h2>
    <img src="/photo/${m.id}" alt="" style="max-height:240px;max-width:100%;object-fit:contain;align-self:center;border-radius:8px">
    ${field("caption", "Caption", m.caption, { placeholder: "Who, where, what's happening" })}
    ${field("date", "Date taken", m.date, { placeholder: "e.g. c. 1955" })}
    <div class="field"><span>Who's in it</span><div id="photoPeople"></div></div>
    <div class="modal-actions">
      <button type="submit" value="delete" class="danger left">Delete photo</button>
      <button type="submit" value="cancel" class="ghost">Cancel</button>
      <button type="submit" value="save">Save</button>
    </div>`, {
    onReady(form) { people = makeMultiPicker(m.person_ids); $("#photoPeople", form).appendChild(people.el); },
    async onSubmit(fd, action) {
      if (action === "delete") {
        if (!confirm("Delete this photo from the family archive? This can't be undone.")) return false;
        await api("DELETE", `/api/media/${m.id}`);
        await refresh();
      } else {
        await api("PUT", `/api/media/${m.id}`, { caption: fd.get("caption"), date: fd.get("date"), person_ids: people.value });
      }
      renderPhotos();
      if (state.selected) openPanel(state.selected, true);
    },
  });
}

function lightbox(m, person) {
  openModal(`
    <img src="/photo/${m.id}" alt="${esc(m.caption)}">
    ${m.caption || m.date ? `<p style="text-align:center;margin:0">${esc(m.caption)}${m.date ? ` <span class="muted">· ${esc(m.date)}</span>` : ""}</p>` : ""}
    <div class="modal-actions">
      ${person ? `<button type="submit" value="portrait" class="ghost left">Use as ${esc(person.given_names || "their")}'s portrait</button>` : ""}
      <button type="submit" value="details" class="ghost">Edit details</button>
      <button type="submit" value="cancel">Close</button>
    </div>`, {
    wide: true,
    async onSubmit(fd, action) {
      if (action === "portrait") {
        await api("PUT", `/api/people/${person.id}`, { portrait_id: m.id });
        await refresh();
        toast("Portrait set.");
      }
      if (action === "details") {
        const full = (await api("GET", "/api/media")).find((x) => x.id === m.id);
        setTimeout(() => photoModal(full), 0);
      }
    },
  });
}

// ------------------------------------------------------------------ relationship finder
let kinA, kinB;
async function runKin() {
  const out = $("#kinResult");
  if (!kinA.value || !kinB.value) { out.innerHTML = ""; return; }
  const r = await api("GET", `/api/relationship?a=${kinA.value}&b=${kinB.value}`);
  const list = (rels) => `<ul>${rels.map((x) => `<li><b>${esc(x.label)}</b>${x.via.length ? ` <span class="muted">— through ${esc(x.via.join(" & "))}</span>` : ""}</li>`).join("")}</ul>`;
  const same = JSON.stringify(r.legal.map((x) => x.label)) === JSON.stringify(r.genetic.map((x) => x.label));
  out.innerHTML = `
    <div class="kin-card">
      <div class="big">${esc(r.summary)}</div>
      ${same && r.genetic.length ? `<h4>Related through</h4>${list(r.genetic)}` : ""}
      ${!same && r.legal.length ? `<h4>Legally, including adoption</h4>${list(r.legal)}` : ""}
      ${!same && r.genetic.length ? `<h4>By blood</h4>${list(r.genetic)}` : ""}
      ${r.other.length ? `<h4>Also</h4><ul>${r.other.map((o) => `<li>${esc(o)}</li>`).join("")}</ul>` : ""}
      <p class="hint" style="margin-top:12px">Read as: “${esc(r.b)} is ${esc(r.a)}'s …”</p>
    </div>`;
}

// ------------------------------------------------------------------ tabs & wiring
function switchTab(name) {
  $$(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab").forEach((t) => t.classList.toggle("active", t.id === `tab-${name}`));
  if (name === "stories") renderStories();
  if (name === "photos") renderPhotos();
  if (name === "people") renderPeople();
  if (name === "tree") requestAnimationFrame(() => renderTree());
}

function gotoPerson(id) {
  switchTab("tree");
  setFocus(id);
  openPanel(id);
}

async function importGedcom(file) {
  const text = await file.text();
  const res = await api("POST", "/api/import-gedcom", { text });
  toast(`Imported ${res.people || 0} people, ${res.couples || 0} couples, ${res["parent links"] || 0} parent links${res.stories ? `, ${res.stories} stories` : ""}.`);
  state.focus = null;
  await refresh();
}

let focusPicker;
async function init() {
  focusPicker = makePicker({ placeholder: "Pick a person…", onPick: (id) => id && setFocus(id) });
  $("#focusPicker").appendChild(focusPicker.el);
  kinA = makePicker({ onPick: runKin });
  kinB = makePicker({ onPick: runKin });
  $("#kinA").appendChild(kinA.el);
  $("#kinB").appendChild(kinB.el);
  $("#kinSwap").onclick = () => { const a = kinA.value; kinA.set(kinB.value); kinB.set(a); runKin(); };

  for (const id of ["genUp", "genDown"]) {
    const sel = $(`#${id}`);
    sel.innerHTML = [1, 2, 3, 4, 5, 6, 8, 10].map((n) => `<option value="${n}">${n}</option>`).join("") + `<option value="99">all</option>`;
    sel.value = store(`heirloom.${id}`) || "3";
    sel.onchange = () => {
      store(`heirloom.${id}`, sel.value);
      state.up = Number($("#genUp").value);
      state.down = Number($("#genDown").value);
      state.fitNext = true;
      renderTree();
    };
  }
  state.up = Number($("#genUp").value);
  state.down = Number($("#genDown").value);

  $$(".tabs button").forEach((b) => (b.onclick = () => switchTab(b.dataset.tab)));
  $("#addPersonBtn").onclick = $("#addPersonBtn2").onclick = $("#emptyAdd").onclick = () => personModal();
  $("#emptySample").onclick = async () => { await api("POST", "/api/sample"); state.focus = null; await refresh(); toast("Loaded the example family. Try “How are we related?” with Emma and Samuel."); };
  $("#dataBtn").onclick = (e) => { e.stopPropagation(); $("#dataMenu").hidden = !$("#dataMenu").hidden; };
  document.addEventListener("click", () => ($("#dataMenu").hidden = true));
  $("#importBtn").onclick = $("#emptyImport").onclick = () => $("#gedFile").click();
  $("#gedFile").onchange = async (e) => {
    const f = e.target.files[0];
    e.target.value = "";
    if (!f) return;
    try { await importGedcom(f); } catch (ex) { toast(ex.message); }
  };
  $("#peopleSearch").oninput = renderPeople;
  $("#storySearch").oninput = renderStories;
  $("#peopleBody").onclick = (e) => { const tr = e.target.closest("tr[data-id]"); if (tr) gotoPerson(Number(tr.dataset.id)); };
  $("#addStoryBtn").onclick = () => storyModal(null);
  $("#storyList").onclick = (e) => {
    const t = e.target.closest("button");
    if (!t) return;
    if (t.dataset.goto) gotoPerson(Number(t.dataset.goto));
    if (t.dataset.edit) storyModal(Number(t.dataset.edit));
  };
  $("#photoFiles").onchange = async (e) => { await uploadFiles(e.target.files); e.target.value = ""; renderPhotos(); };
  $("#photoGrid").onclick = (e) => {
    const t = e.target.closest("[data-goto],[data-edit],[data-view]");
    if (!t) return;
    if (t.dataset.goto) gotoPerson(Number(t.dataset.goto));
    const m = mediaCache.find((x) => x.id === Number(t.dataset.edit || t.dataset.view));
    if (t.dataset.edit) photoModal(m);
    if (t.dataset.view) lightbox(m, null);
  };
  $("#familyName").onclick = () => openModal(`
    <h2>Family name</h2>
    ${field("family_name", "Shown at the top of the page", state.meta.family_name)}
    <div class="modal-actions"><button type="submit" value="cancel" class="ghost">Cancel</button><button type="submit" value="save">Save</button></div>`, {
    async onSubmit(fd) { await api("PUT", "/api/meta", { family_name: fd.get("family_name") }); await refresh(); },
  });
  $("#familyName").onkeydown = (e) => { if (e.key === "Enter") $("#familyName").click(); };
  window.addEventListener("resize", () => applyView());
  setupPanZoom();
  await refresh();
}

init().catch((e) => {
  document.body.innerHTML = `<p style="padding:24px">Couldn't reach Heirloom: ${esc(e.message)}. Is the program still running?</p>`;
});
