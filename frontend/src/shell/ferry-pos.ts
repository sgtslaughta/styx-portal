const KEY = "styx.ferry";
export type FerryPos = { side: "left" | "right"; y: number };
const DEFAULT: FerryPos = { side: "right", y: 0.5 };
export const clampY = (y: number) => Math.min(0.9, Math.max(0.1, y));
export const snapSide = (x: number, width: number): FerryPos["side"] => (x < width / 2 ? "left" : "right");
export function readPos(): FerryPos {
  try {
    const p = JSON.parse(localStorage.getItem(KEY) ?? "null");
    if (p && (p.side === "left" || p.side === "right") && typeof p.y === "number") return { side: p.side, y: clampY(p.y) };
  } catch { /* private mode / bad JSON */ }
  return DEFAULT;
}
export function writePos(p: FerryPos) { try { localStorage.setItem(KEY, JSON.stringify(p)); } catch { /* ignore */ } }

/** While the edge tab is dragged, body[data-ferry-drag] turns the iframe's pointer events off (see globals.css),
 *  so the pointer stream stays on the shell document instead of entering the app. */
export function markDragging(on: boolean) { document.body.toggleAttribute("data-ferry-drag", on); }
