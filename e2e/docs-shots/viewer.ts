// Mock of the streamed-desktop viewer (the real one is the selkies web client served by the workstation
// agent, which needs a live seat): a generic desktop plus a stream-settings side panel in the same spirit.
import { desktopHtml, type Scene } from "./scenes";

const ROWS: [string, string][] = [["Encoder", "HEVC (NVENC)"], ["Resolution", "2560 x 1440"], ["Framerate", "60 fps"], ["Bitrate", "20 Mbps"], ["Scaling", "125 %"]];
const TOGGLES: [string, boolean][] = [["Clipboard sync", true], ["Audio", true], ["Gamepad", false], ["Show cursor", true]];

export function viewerHtml(scene: Scene, panel: boolean): string {
  const base = desktopHtml(scene, 1440, 900);
  if (!panel) return base;
  const css = `<style>
.sp{position:fixed;top:0;right:0;bottom:0;width:330px;background:rgba(14,22,28,.94);border-left:1px solid rgba(255,255,255,.1);color:#e6edf0;font:13px/1.4 system-ui,sans-serif;padding:22px 20px;backdrop-filter:blur(10px)}
.sp h3{font-size:15px;margin-bottom:4px}.sp p{color:#8fa3ab;font-size:12px;margin-bottom:18px}.sp .r{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px solid rgba(255,255,255,.07)}
.sp .r b{font-weight:500;color:#6FB7BC}.sp .bar{height:6px;border-radius:3px;background:#24343c;margin:6px 0 16px}.sp .bar i{display:block;height:100%;width:62%;border-radius:3px;background:#6FB7BC}
.sp .t{display:flex;justify-content:space-between;align-items:center;padding:9px 0}.sp .sw{width:34px;height:19px;border-radius:10px;background:#2c3d45;position:relative}.sp .sw.on{background:#6FB7BC}
.sp .sw:after{content:"";position:absolute;top:2px;left:2px;width:15px;height:15px;border-radius:50%;background:#fff}.sp .sw.on:after{left:17px}
.sp h4{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#8fa3ab;margin:20px 0 6px}.live{display:inline-block;width:8px;height:8px;border-radius:50%;background:#34d399;margin-right:6px}</style>`;
  const html = `<div class="sp"><h3>studio-pc</h3><p><span class="live"></span>Streaming - 4 ms - 0.0% loss</p><h4>Stream</h4>
${ROWS.map(([k, v]) => `<div class="r"><span>${k}</span><b>${v}</b></div>`).join("")}<h4>Quality</h4><div class="bar"><i></i></div>
<h4>Options</h4>${TOGGLES.map(([k, on]) => `<div class="t"><span>${k}</span><span class="sw${on ? " on" : ""}"></span></div>`).join("")}</div>`;
  return base.replace("</style>", () => "</style>" + css) + html;
}
