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

window.convert = async (mmd) => {
  const { elements, files } = await parseMermaidToExcalidraw(mmd, { fontSize: 18 });
  const converted = convertToExcalidrawElements(elements, { regenerateIds: false });
  applyClassDefs(mmd, converted);
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
  if (dark) scene = { ...scene, elements: scene.elements.map((e) => e.customData?.styx ? { ...e, strokeColor: preDark(e.strokeColor), backgroundColor: preDark(e.backgroundColor) } : e) };
  const svg = await exportToSvg({
    elements: scene.elements,
    appState: { ...scene.appState, exportBackground: false, exportWithDarkMode: dark },
    files: scene.files || {},
    exportPadding: 16,
  });
  return svg.outerHTML;
};
