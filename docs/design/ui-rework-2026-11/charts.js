// Tiny SVG charts for the mockup: line (multi-series, crosshair tooltip), bars (single series), hbars.
// Colours come from CSS vars --s1..--s4 (validated palette); text uses ink tokens only.
const NS = "http://www.w3.org/2000/svg";
const el = (t, a = {}, p) => { const e = document.createElementNS(NS, t); for (const k in a) e.setAttribute(k, a[k]); p && p.append(e); return e; };
const tip = Object.assign(document.createElement("div"), { className: "viz-tip" }); document.body.append(tip);
const showTip = (e, html) => { tip.innerHTML = html; tip.style.opacity = 1; tip.style.left = e.clientX + 14 + "px"; tip.style.top = e.clientY - 10 + "px"; };
const hideTip = () => (tip.style.opacity = 0);
const nice = (m) => { const p = 10 ** Math.floor(Math.log10(m)), n = m / p; return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p; };

function frame(host, h) {
  host.innerHTML = ""; h = Math.max(h, host.clientHeight); const W = host.clientWidth, svg = el("svg", { width: W, height: h, viewBox: `0 0 ${W} ${h}`, role: "img" }, host);
  return { svg, W, H: h, L: 36, R: 8, T: 8, B: 22 };
}
function yAxis(f, max, fmt) {
  for (let i = 0; i <= 4; i++) { const v = (max / 4) * i, y = f.H - f.B - ((f.H - f.T - f.B) * i) / 4;
    el("line", { x1: f.L, x2: f.W - f.R, y1: y, y2: y, class: i ? "grid" : "base" }, f.svg);
    el("text", { x: f.L - 6, y: y + 4, "text-anchor": "end", class: "ax" }, f.svg).textContent = fmt(v); }
}

// series: [{name, color: 's1', data: [..]}], labels: x labels
function line(host, { series, labels, max, fmt = (v) => v, unit = "", h = 170 }) {
  const f = frame(host, h); max ??= nice(Math.max(...series.flatMap((s) => s.data)));
  yAxis(f, max, fmt); const n = labels.length, x = (i) => f.L + ((f.W - f.L - f.R) * i) / (n - 1), y = (v) => f.H - f.B - ((f.H - f.T - f.B) * v) / max;
  labels.forEach((l, i) => { if (i % Math.ceil(n / 6) === 0) el("text", { x: x(i), y: f.H - 6, "text-anchor": "middle", class: "ax" }, f.svg).textContent = l; });
  for (const s of series) el("path", { d: s.data.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(""), class: "ln", stroke: `var(--${s.color})` }, f.svg);
  // direct label at the line end (<= 4 series)
  for (const s of series) el("text", { x: f.W - f.R - 2, y: y(s.data.at(-1)) - 6, "text-anchor": "end", class: "dl" }, f.svg).textContent = s.name;
  const cross = el("line", { y1: f.T, y2: f.H - f.B, class: "cross" }, f.svg), dots = series.map((s) => el("circle", { r: 4, class: "dot", fill: `var(--${s.color})` }, f.svg));
  const hit = el("rect", { x: f.L, y: 0, width: f.W - f.L - f.R, height: f.H, fill: "transparent" }, f.svg);
  hit.onpointermove = (e) => { const r = f.svg.getBoundingClientRect(), i = Math.max(0, Math.min(n - 1, Math.round(((e.clientX - r.left - f.L) / (f.W - f.L - f.R)) * (n - 1))));
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.style.opacity = 1;
    dots.forEach((d, k) => { d.setAttribute("cx", x(i)); d.setAttribute("cy", y(series[k].data[i])); d.style.opacity = 1; });
    showTip(e, `<b>${labels[i]}</b>` + series.map((s) => `<div><i style="background:var(--${s.color})"></i>${s.name}<span>${fmt(s.data[i])}${unit}</span></div>`).join("")); };
  hit.onpointerleave = () => { hideTip(); cross.style.opacity = 0; dots.forEach((d) => (d.style.opacity = 0)); };
}

// data: [{label, value, note?, ghost?}] — ghost = projected (textured)
function bars(host, { data, color = "s1", fmt = (v) => v, unit = "", h = 170, ref }) {
  const f = frame(host, h), max = nice(Math.max(...data.map((d) => d.value), ref?.value ?? 0)); yAxis(f, max, fmt);
  const n = data.length, bw = (f.W - f.L - f.R) / n, y = (v) => f.H - f.B - ((f.H - f.T - f.B) * v) / max;
  data.forEach((d, i) => {
    const x = f.L + i * bw + 1, w = Math.max(2, bw - 2), top = y(d.value), hh = f.H - f.B - top;
    const r = Math.min(4, w / 2, hh);
    el("path", { d: `M${x},${f.H - f.B}V${top + r}q0,-${r} ${r},-${r}h${w - 2 * r}q${r},0 ${r},${r}V${f.H - f.B}Z`, fill: d.ghost ? "url(#tex)" : `var(--${color})`, class: d.ghost ? "ghost" : "" }, f.svg);
    if (i % Math.ceil(n / 8) === 0) el("text", { x: x + w / 2, y: f.H - 6, "text-anchor": "middle", class: "ax" }, f.svg).textContent = d.label;
    const hit = el("rect", { x: f.L + i * bw, y: f.T, width: bw, height: f.H - f.T - f.B, fill: "transparent" }, f.svg);
    hit.onpointermove = (e) => showTip(e, `<b>${d.label}</b><div>${d.ghost ? "Projected" : "Value"}<span>${fmt(d.value)}${unit}</span></div>${d.note ? `<div class="n">${d.note}</div>` : ""}`); hit.onpointerleave = hideTip;
  });
  const defs = el("defs", {}, f.svg), pat = el("pattern", { id: "tex", width: 6, height: 6, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" }, defs);
  el("rect", { width: 6, height: 6, fill: `var(--${color})`, opacity: .18 }, pat); el("line", { x1: 0, y1: 0, x2: 0, y2: 6, stroke: `var(--${color})`, "stroke-width": 2 }, pat);
  if (ref) { const yy = y(ref.value); el("line", { x1: f.L, x2: f.W - f.R, y1: yy, y2: yy, class: "ref" }, f.svg);
    el("text", { x: f.W - f.R, y: yy - 5, "text-anchor": "end", class: "dl" }, f.svg).textContent = ref.label; }
}

// rows: [{label, value, sub?}] horizontal bars, labels left, value right (ink colour)
function hbars(host, { rows, color = "s1", fmt = (v) => v, unit = "" }) {
  host.innerHTML = ""; const max = Math.max(...rows.map((r) => r.value));
  for (const r of rows) { const d = document.createElement("div"); d.className = "hb";
    d.innerHTML = `<span class="hb-l">${r.label}${r.sub ? `<small>${r.sub}</small>` : ""}</span><span class="hb-t"><i style="width:${(r.value / max) * 100}%;background:var(--${color})"></i></span><span class="hb-v tabular">${fmt(r.value)}${unit}</span>`;
    d.onpointermove = (e) => showTip(e, `<b>${r.label}</b><div>${unit.trim() || "Value"}<span>${fmt(r.value)}${unit}</span></div>`); d.onpointerleave = hideTip; host.append(d); }
}

// Stacked horizontal bars: rows [{label, sub?, parts: {seriesName: value}}], series [{name, color}]
function hstack(host, { rows, series, fmt = (v) => v, unit = "" }) {
  host.innerHTML = ""; const tot = (r) => series.reduce((a, s) => a + (r.parts[s.name] || 0), 0), max = Math.max(...rows.map(tot));
  for (const r of rows) {
    const d = document.createElement("div"); d.className = "hb";
    d.innerHTML = `<span class="hb-l">${r.label}${r.sub ? `<small>${r.sub}</small>` : ""}</span><span class="hb-t stack"></span><span class="hb-v tabular">${fmt(tot(r))}${unit}</span>`;
    const track = d.querySelector(".stack");
    for (const s of series) { const v = r.parts[s.name]; if (!v) continue;
      const seg = document.createElement("i"); seg.style.cssText = `width:${(v / max) * 100}%;background:var(--${s.color})`;
      seg.onpointermove = (e) => showTip(e, `<b>${r.label}</b><div><i style="background:var(--${s.color})"></i>${s.name}<span>${fmt(v)}${unit}</span></div>`); seg.onpointerleave = hideTip;
      track.append(seg); }
    host.append(d);
  }
}

// Top-N folding: keep the N largest, fold the rest into "Others" (neutral grey, never a new hue).
const SLOTS = ["s1", "s2", "s3", "s4", "s5"];
function topRows(rows, n, val) {
  const sorted = [...rows].sort((a, b) => val(b) - val(a)); if (sorted.length <= n) return sorted;
  return [...sorted.slice(0, n), { label: `Others`, sub: `${sorted.length - n} more`, others: sorted.slice(n) }];
}
// Workstation × user streaming time: top 5 users get colours, the rest become "Others"; top 5 workstations, rest fold into one row.
function streamTime(host, legendHost, { rows, n = 5, fmt, unit }) {
  const users = {}; rows.forEach((r) => Object.entries(r.parts).forEach(([u, v]) => (users[u] = (users[u] || 0) + v)));
  const top = Object.keys(users).sort((a, b) => users[b] - users[a]).slice(0, n);
  const series = top.map((u, i) => ({ name: u, color: SLOTS[i] })); if (Object.keys(users).length > n) series.push({ name: "Others", color: "s0" });
  const fold = (parts) => { const o = {}; for (const [u, v] of Object.entries(parts)) { const k = top.includes(u) ? u : "Others"; o[k] = (o[k] || 0) + v; } return o; };
  const sum = (p) => Object.values(p).reduce((a, b) => a + b, 0);
  const merge = (list) => list.reduce((acc, o) => { for (const [u, v] of Object.entries(o.parts)) acc[u] = (acc[u] || 0) + v; return acc; }, {});
  const out = topRows(rows, n, (r) => sum(r.parts)).map((r) => ({ label: r.label, sub: r.sub, parts: fold(r.others ? merge(r.others) : r.parts) }));
  legendHost.innerHTML = series.map((s) => `<span><i style="background:var(--${s.color})"></i>${s.name}</span>`).join("");
  hstack(host, { rows: out, series, fmt, unit });
}

// Sparkline for stat tiles: 2px line + soft area, last point dotted, hover shows value.
function spark(host, { data, color = "s1", fmt = (v) => v, labels }) {
  host.innerHTML = ""; const W = host.clientWidth, H = host.clientHeight || 34, mn = Math.min(...data), mx = Math.max(...data), pad = 3;
  const x = (i) => (W * i) / (data.length - 1), y = (v) => H - pad - ((H - 2 * pad) * (v - mn)) / (mx - mn || 1);
  const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}` }, host), pts = data.map((v, i) => `${x(i)},${y(v)}`).join(" L");
  el("path", { d: `M0,${H} L${pts} L${W},${H}Z`, fill: `var(--${color})`, opacity: .12 }, svg);
  el("path", { d: `M${pts}`, fill: "none", stroke: `var(--${color})`, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
  el("circle", { cx: x(data.length - 1), cy: y(data.at(-1)), r: 3, fill: `var(--${color})` }, svg);
  svg.onpointermove = (e) => { const r = svg.getBoundingClientRect(), i = Math.round(((e.clientX - r.left) / W) * (data.length - 1)); showTip(e, `<b>${labels ? labels[i] : ""}</b><div>Value<span>${fmt(data[i])}</span></div>`); };
  svg.onpointerleave = hideTip;
}
