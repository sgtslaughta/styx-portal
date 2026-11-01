// Browser-side entry, bundled by esbuild. Exposes convert() and render() to run.mjs.
import { parseMermaidToExcalidraw } from "@excalidraw/mermaid-to-excalidraw";
import { convertToExcalidrawElements, exportToSvg } from "@excalidraw/excalidraw";

// The converter drops classDef styling: re-apply fill/stroke to shapes by mermaid node id.
function applyClassDefs(mmd, elements) {
  const defs = {};
  for (const [, name, body] of mmd.matchAll(/^\s*classDef\s+(\w+)\s+(.+)$/gm)) {
    const d = {};
    for (const kv of body.split(",")) { const [k, v] = kv.split(":"); d[k.trim()] = v?.trim(); }
    defs[name] = d;
  }
  const role = {};
  const flat = mmd.replace(/"[^"\n]*"/g, '""');
  for (const [, id, r] of flat.matchAll(/(\w+)\s*(?:[(\[{][^\n:]*?[)\]}])*\s*:::(\w+)/g)) role[id] = r;
  for (const [, ids, r] of mmd.matchAll(/^\s*class\s+([\w,\s]+?)\s+(\w+)\s*$/gm))
    for (const id of ids.split(",")) role[id.trim()] = r;
  for (const el of elements) {
    const d = defs[role[el.id]];
    if (!d || el.type === "text" || el.type === "arrow") continue;
    if (d.fill) { el.backgroundColor = d.fill; el.fillStyle = "solid"; }
    if (d.stroke) el.strokeColor = d.stroke;
    el.customData = { styx: 1 };
    if (d.fill) for (const t of elements) if (t.type === "text" && t.containerId === el.id) { t.strokeColor = "#ffffff"; t.customData = { styx: 1 }; }
    if (d["stroke-width"]) el.strokeWidth = parseFloat(d["stroke-width"]) || 2;
  }
}

// Edge labels: the converter centres them on their arrow, so they cross lines and pile up where
// edges fan out. Unbind them, lift sequence labels above the arrow, push overlapping labels apart,
// and back each with a page-coloured box (like Mermaid's label background).
const PAD = 4;
const hit = (a, b) => a.x < b.x + b.width + PAD && b.x < a.x + a.width + PAD &&
  a.y < b.y + b.height + PAD && b.y < a.y + a.height + PAD;
function tidyLabels(mmd, els) {
  const byId = Object.fromEntries(els.map((e) => [e.id, e]));
  const seq = /^\s*sequenceDiagram/m.test(mmd);
  const labels = els.filter((t) => t.type === "text" && byId[t.containerId]?.type === "arrow");
  for (const t of labels) {
    const a = byId[t.containerId];
    a.boundElements = (a.boundElements || []).filter((b) => b.id !== t.id);
    t.containerId = null;
    const [p0, p1] = [a.points[0], a.points[a.points.length - 1]];
    if (seq && Math.abs(p1[1] - p0[1]) < 2) t.y = a.y + p0[1] - t.height - 6;
  }
  for (let pass = 0; pass < 20; pass++) {
    let moved = false;
    labels.sort((a, b) => a.y - b.y || a.x - b.x);
    for (let i = 0; i < labels.length; i++)
      for (let j = i + 1; j < labels.length; j++)
        if (hit(labels[i], labels[j])) { labels[j].y = labels[i].y + labels[i].height + PAD; moved = true; }
    if (!moved) break;
  }
  if (seq) return els;
  const out = [];
  for (const e of els) {
    if (labels.includes(e)) {
      const [bg] = convertToExcalidrawElements([{ type: "rectangle", x: e.x - 3, y: e.y - 1,
        width: e.width + 6, height: e.height + 2, backgroundColor: "#ffffff", fillStyle: "solid",
        strokeColor: "transparent", roughness: 0, strokeWidth: 1 }]);
      bg.customData = { styxBg: 1 };
      out.push(bg);
    }
    out.push(e);
  }
  return out;
}

window.convert = async (mmd) => {
  const { elements, files } = await parseMermaidToExcalidraw(mmd, { fontSize: 18 });
  let converted = convertToExcalidrawElements(elements, { regenerateIds: false });
  applyClassDefs(mmd, converted);
  converted = tidyLabels(mmd, converted);
  return {
    type: "excalidraw",
    version: 2,
    source: "styx-diagrams",
    elements: converted,
    appState: { viewBackgroundColor: "#ffffff" },
    files: files || {},
  };
};

// Excalidraw dark export = CSS invert(93%) hue-rotate(180deg), which greys out brand colours.
// Pre-compensate styx-coloured elements with the inverse so they come out as authored.
const H = [[-0.574, 1.43, 0.144], [0.426, 0.43, 0.144], [0.426, 1.43, -0.856]];
const inv = (a) => { // 3x3 inverse via adjugate
  const [[p, q, r], [s, t, u], [v, w, x]] = a;
  const det = p * (t * x - u * w) - q * (s * x - u * v) + r * (s * w - t * v);
  return [[(t * x - u * w), (r * w - q * x), (q * u - r * t)], [(u * v - s * x), (p * x - r * v), (r * s - p * u)], [(s * w - t * v), (q * v - p * w), (p * t - q * s)]].map((row) => row.map((c) => c / det));
};
const HI = inv(H);
function preDark(hex) {
  if (!/^#[0-9a-f]{6}$/i.test(hex)) return hex;
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const y = HI.map((row) => row[0] * c[0] + row[1] * c[1] + row[2] * c[2]);
  const x = y.map((v) => Math.min(1, Math.max(0, (v - 0.93) / -0.86)));
  return "#" + x.map((v) => Math.round(v * 255).toString(16).padStart(2, "0")).join("");
}

window.render = async (scene, dark) => {
  if (dark) scene = { ...scene, elements: scene.elements.map((e) =>
    e.customData?.styxBg ? { ...e, backgroundColor: preDark("#0d1117") } // GitHub dark page
    : e.customData?.styx ? { ...e, strokeColor: preDark(e.strokeColor), backgroundColor: preDark(e.backgroundColor) } : e) };
  const svg = await exportToSvg({
    elements: scene.elements,
    appState: { ...scene.appState, exportBackground: false, exportWithDarkMode: dark },
    files: scene.files || {},
    exportPadding: 16,
  });
  return svg.outerHTML;
};
