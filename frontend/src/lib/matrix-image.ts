const COLS = ["A", "B", "C", "D", "E"];
const CELL_W = 110, CELL_H = 44, HEAD = 40, TOP = 76, PAD = 20;

/** Render the sign-in card grid (A-E x 1-10) onto a canvas. */
export function drawCard(canvas: HTMLCanvasElement, cells: Record<string, string>, title: string): void {
  const w = PAD * 2 + HEAD + CELL_W * COLS.length;
  const h = TOP + HEAD + CELL_H * 10 + PAD;
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#111111";
  ctx.textBaseline = "middle";
  ctx.font = "bold 22px sans-serif";
  ctx.fillText(title, PAD, 28);
  ctx.font = "12px sans-serif";
  ctx.fillText(new Date().toISOString().slice(0, 10), PAD, 52);
  ctx.textAlign = "center";
  ctx.font = "bold 16px monospace";
  const x0 = PAD + HEAD;
  const y0 = TOP + HEAD;
  COLS.forEach((c, i) => ctx.fillText(c, x0 + CELL_W * i + CELL_W / 2, TOP + HEAD / 2));
  for (let r = 1; r <= 10; r++) {
    const cy = y0 + CELL_H * (r - 1) + CELL_H / 2;
    ctx.font = "bold 16px monospace";
    ctx.fillText(String(r), PAD + HEAD / 2, cy);
    ctx.font = "20px monospace";
    COLS.forEach((c, i) => ctx.fillText(cells[`${c}${r}`] ?? "", x0 + CELL_W * i + CELL_W / 2, cy));
  }
  ctx.strokeStyle = "#999999";
  for (let i = 0; i <= 10; i++) {
    ctx.beginPath(); ctx.moveTo(PAD, y0 + CELL_H * i); ctx.lineTo(w - PAD, y0 + CELL_H * i); ctx.stroke();
  }
  for (let i = 0; i <= COLS.length; i++) {
    ctx.beginPath(); ctx.moveTo(x0 + CELL_W * i, TOP); ctx.lineTo(x0 + CELL_W * i, h - PAD); ctx.stroke();
  }
}

export function cardPngBlob(cells: Record<string, string>, title: string): Promise<Blob> {
  const canvas = document.createElement("canvas");
  drawCard(canvas, cells, title);
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("PNG export failed"))), "image/png"));
}
