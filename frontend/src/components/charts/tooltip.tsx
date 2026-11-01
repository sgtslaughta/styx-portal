/** One shared tooltip element for every chart (a single node appended to <body>). Text stays in ink colours. */
export type TipRow = { color?: string; name: string; value: string };
export type TipContent = { title?: string; rows: TipRow[]; note?: string };

let node: HTMLDivElement | null = null;

function host(): HTMLDivElement {
  if (node && node.isConnected) return node;
  node = document.createElement("div");
  node.setAttribute("role", "tooltip");
  node.style.cssText =
    "position:fixed;z-index:50;pointer-events:none;display:none;min-width:140px;padding:8px 10px;border-radius:8px;" +
    "font:12.5px/1.5 system-ui,sans-serif;background:var(--popover);color:var(--foreground);" +
    "border:1px solid var(--border);box-shadow:0 6px 20px rgb(0 0 0 / 0.18)";
  document.body.append(node);
  return node;
}

const el = (tag: string, css: string, text?: string) => {
  const e = document.createElement(tag);
  e.style.cssText = css;
  if (text !== undefined) e.textContent = text;
  return e;
};

export function showTip(e: { clientX: number; clientY: number }, c: TipContent) {
  const n = host();
  n.replaceChildren();
  if (c.title) n.append(el("b", "display:block;margin-bottom:2px;font-weight:600", c.title));
  for (const r of c.rows) {
    const d = el("div", "display:flex;align-items:center;gap:6px;color:var(--muted-foreground)");
    if (r.color) d.append(el("i", `width:8px;height:8px;border-radius:2px;flex:none;background:${r.color}`));
    // "CPU 22%": the measure is named, never a bare "Value".
    d.append(el("span", "", `${r.name} `), el("span", "margin-left:auto;padding-left:12px;color:var(--foreground);font-variant-numeric:tabular-nums", r.value));
    n.append(d);
  }
  if (c.note) n.append(el("div", "color:var(--muted-foreground);font-size:11.5px", c.note));
  n.style.display = "block";
  const w = n.offsetWidth || 160;
  const left = e.clientX + 14 + w > window.innerWidth ? e.clientX - w - 14 : e.clientX + 14;
  n.style.left = `${Math.max(4, left)}px`;
  n.style.top = `${e.clientY - 10}px`;
}

export function hideTip() {
  if (node) node.style.display = "none";
}
