// Self-rendered generic Linux desktop scenes (HTML) used for workstation/desktop thumbnails and the
// viewer mock. Pure demo content: no real hostnames, users or data.
export type Scene = "code" | "render" | "browser" | "terminal" | "files";

const ICONS = ["#e95420", "#3b82f6", "#10b981", "#f59e0b", "#a855f7", "#ef4444", "#06b6d4"];

const win = (x: number, y: number, w: number, h: number, title: string, body: string) =>
  `<div class="win" style="left:${x}px;top:${y}px;width:${w}px;height:${h}px">
     <div class="tb"><i></i><i></i><i></i><span>${title}</span></div><div class="bd">${body}</div></div>`;

const codeBody = () => {
  const L = [
    ["#c678dd", "import", "#e5e9f0", " asyncio"], ["#c678dd", "from", "#e5e9f0", " styx.agent import Seat, Stream"],
    ["", "", "", ""], ["#c678dd", "async def", "#61afef", " main():"],
    ["#7f848e", "    # pick the best encoder for this GPU", "", ""],
    ["#e5e9f0", "    seat = await Seat.start(", "#98c379", "\"studio-pc\"", "#e5e9f0", ")"],
    ["#e5e9f0", "    stream = Stream(seat, codec=", "#98c379", "\"hevc\"", "#e5e9f0", ", fps=", "#d19a66", "60", "#e5e9f0", ")"],
    ["#c678dd", "    async with", "#e5e9f0", " stream:"], ["#e5e9f0", "        await stream.serve_forever()"],
    ["", "", "", ""], ["#c678dd", "if", "#e5e9f0", " __name__ == ", "#98c379", "\"__main__\"", "#e5e9f0", ":"],
    ["#e5e9f0", "    asyncio.run(main())"],
  ];
  const lines = L.map((l, i) => {
    let s = "";
    for (let k = 0; k < l.length; k += 2) s += `<span style="color:${l[k] || "#e5e9f0"}">${l[k + 1]}</span>`;
    return `<div><b>${i + 1}</b>${s || "&nbsp;"}</div>`;
  }).join("");
  return `<div class="code">${lines}</div>`;
};

const termBody = () => `<div class="term"><div><span class="g">alice@studio-pc</span>:<span class="b">~/projects</span>$ nvidia-smi --query-gpu=name,utilization.gpu --format=csv</div>
<div>name, utilization.gpu [%]</div><div>NVIDIA GeForce RTX 4070, 38 %</div>
<div><span class="g">alice@studio-pc</span>:<span class="b">~/projects</span>$ docker compose up -d</div>
<div>[+] Running 4/4</div><div> ✔ Container api&nbsp;&nbsp;&nbsp;Started</div><div> ✔ Container db&nbsp;&nbsp;&nbsp;&nbsp;Started</div>
<div><span class="g">alice@studio-pc</span>:<span class="b">~/projects</span>$ <u></u></div></div>`;

const renderBody = () => `<div class="vp"><svg viewBox="0 0 800 520" width="100%" height="100%" preserveAspectRatio="xMidYMid slice">
  <defs><linearGradient id="f" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3a3f4b"/><stop offset="1" stop-color="#23262e"/></linearGradient></defs>
  <rect width="800" height="520" fill="url(#f)"/>
  <g stroke="#555b69" stroke-width="1" opacity=".7">${Array.from({ length: 13 }, (_, i) => `<line x1="${i * 66 - 40}" y1="520" x2="${200 + i * 33}" y2="250"/>`).join("")}
  ${Array.from({ length: 7 }, (_, i) => `<line x1="0" y1="${255 + i * i * 7}" x2="800" y2="${255 + i * i * 7}"/>`).join("")}</g>
  <polygon points="300,170 430,130 560,170 430,215" fill="#f59e0b"/><polygon points="300,170 430,215 430,370 300,320" fill="#d97706"/>
  <polygon points="430,215 560,170 560,320 430,370" fill="#b45309"/>
  <circle cx="610" cy="330" r="62" fill="#6366f1"/><circle cx="592" cy="310" r="22" fill="#a5b4fc" opacity=".55"/>
  <ellipse cx="610" cy="395" rx="70" ry="12" fill="#000" opacity=".35"/>
</svg><div class="gizmo">XYZ</div></div>`;

const browserBody = () => `<div class="br"><div class="url"><span>styx.example.com</span></div>
<div class="cards">${["Sonarr", "Jellyfin", "Grafana", "Notes", "Wiki", "Files"].map((n, i) =>
  `<div class="card"><em style="background:${ICONS[i]}"></em>${n}<small>${i % 3 ? "Healthy" : "Up"}</small></div>`).join("")}</div></div>`;

const filesBody = () => `<div class="fm"><aside>${["Home", "Desktop", "Documents", "Downloads", "Pictures"].map((n) => `<p>${n}</p>`).join("")}</aside>
<main>${["renders", "notes.md", "build.log", "scene-v3.blend", "report.pdf", "assets", "clip.mp4", "todo.txt"].map((n, i) =>
  `<div><em style="background:${ICONS[(i + 2) % 7]}"></em>${n}</div>`).join("")}</main></div>`;

const LAYOUT: Record<Scene, string> = {
  code: win(150, 70, 760, 430, "main.py - Editor", codeBody()) + win(520, 360, 640, 300, "Terminal", termBody()),
  terminal: win(110, 90, 800, 440, "Terminal", termBody()) + win(560, 300, 640, 380, "Files", filesBody()),
  render: win(90, 55, 1100, 620, "scene-v3.blend - 3D viewport", renderBody()),
  browser: win(120, 60, 980, 560, "Browser", browserBody()) + win(760, 400, 460, 270, "Files", filesBody()),
  files: win(180, 80, 760, 440, "Files", filesBody()) + win(620, 300, 600, 340, "Terminal", termBody()),
};

export function desktopHtml(scene: Scene, w = 1280, h = 720, time = "10:42"): string {
  const k = h / 720;
  return `<!doctype html><meta charset="utf-8"><style>
*{box-sizing:border-box;margin:0}html,body{width:${w}px;height:${h}px;overflow:hidden;font:13px/1.35 "Inter","Cantarell",system-ui,sans-serif}
.root{width:1280px;height:720px;transform:scale(${k});transform-origin:0 0;position:relative;
 background:radial-gradient(1200px 700px at 20% 15%,#6d3a8c 0,transparent 60%),radial-gradient(900px 600px at 85% 90%,#e0693b 0,transparent 55%),linear-gradient(135deg,#2a1b4a,#5b2a6a 55%,#a8472f);color:#e8e8ee}
.top{position:absolute;inset:0 0 auto 0;height:28px;background:#0b0b10;display:flex;align-items:center;justify-content:space-between;padding:0 14px;font-size:12.5px;font-weight:600}
.top .r{display:flex;gap:10px;opacity:.9}.dock{position:absolute;left:10px;top:50%;transform:translateY(-46%);background:rgba(20,20,28,.78);border-radius:16px;padding:8px;display:flex;flex-direction:column;gap:8px}
.dock em{width:42px;height:42px;border-radius:11px;display:block}
.win{position:absolute;background:#1e2028;border-radius:11px;overflow:hidden;box-shadow:0 18px 50px rgba(0,0,0,.5),0 0 0 1px rgba(255,255,255,.07);display:flex;flex-direction:column}
.tb{height:34px;background:#2b2e38;display:flex;align-items:center;gap:7px;padding:0 12px;flex:none}.tb i{width:11px;height:11px;border-radius:50%;background:#ef4444}.tb i:nth-child(2){background:#f59e0b}.tb i:nth-child(3){background:#22c55e}
.tb span{margin:0 auto;transform:translateX(-24px);font-size:12px;opacity:.75}.bd{flex:1;min-height:0}
.code{font:12.5px/1.65 "JetBrains Mono","DejaVu Sans Mono",monospace;padding:12px 0;background:#21252b;height:100%}.code b{display:inline-block;width:42px;text-align:right;padding-right:16px;color:#4b5263;font-weight:400}
.term{font:12.5px/1.6 "DejaVu Sans Mono",monospace;padding:12px 14px;background:#16181d;height:100%;color:#d4d7de}.g{color:#7ee787}.b{color:#79c0ff}u{display:inline-block;width:8px;height:15px;background:#d4d7de;vertical-align:-3px}
.vp{position:relative;height:100%}.gizmo{position:absolute;right:18px;top:14px;font-size:11px;letter-spacing:2px;opacity:.6}
.br{background:#f4f5f8;height:100%;color:#1b1d24}.url{height:38px;background:#e6e8ee;padding:8px 14px}.url span{display:block;background:#fff;border-radius:14px;padding:3px 14px;width:60%;font-size:12px}
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;padding:18px}.card{background:#fff;border-radius:10px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.12);font-weight:600}.card em{display:block;width:34px;height:34px;border-radius:9px;margin-bottom:10px}.card small{display:block;color:#16a34a;font-weight:500;margin-top:2px}
.fm{display:flex;height:100%;background:#262932}.fm aside{width:150px;background:#1d1f27;padding:12px}.fm aside p{padding:5px 8px;opacity:.8}.fm aside p:first-child{background:rgba(255,255,255,.08);border-radius:6px}
.fm main{flex:1;display:grid;grid-template-columns:repeat(4,1fr);gap:12px;padding:16px;align-content:start}.fm main div{text-align:center;font-size:12px}.fm main em{display:block;width:52px;height:52px;border-radius:12px;margin:0 auto 6px}
</style><div class="root"><div class="top"><span>Activities</span><span>${time}</span><span class="r"><span>●</span><span>◐</span><span>⏻</span></span></div>
<div class="dock">${ICONS.map((c) => `<em style="background:${c}"></em>`).join("")}</div>${LAYOUT[scene]}</div>`;
}
