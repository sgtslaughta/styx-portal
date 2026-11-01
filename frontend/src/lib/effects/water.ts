// Water surface: CPU height-field wave sim at low res. Mode "image" refracts a source via a
// WebGL2 shader (gold-tintable specular); mode "glass" draws Canvas2D glints. Port of docs/design/ui-rework-2026-11/ripple.js.
export interface WaterOptions {
  mode?: "image" | "glass";
  source?: CanvasImageSource | null;
  scale?: number;
  damping?: number;
  hoverRadius?: number;
  hoverStrength?: number;
  clickRadius?: number;
  clickStrength?: number;
  refract?: number;
  light?: number;
  tint?: [number, number, number];
  idleDrops?: { every: [number, number]; radius: number; strength: number } | null;
}
export interface Water {
  drop(x: number, y: number, radius: number, strength: number): void;
  setSource(img: CanvasImageSource): void;
  destroy(): void;
}

const STOP_PEAK = 0.004; // absolute, not scaled by grid size

const VS = `#version 300 es
in vec2 p; out vec2 uv; void main() { uv = p * .5 + .5; uv.y = 1. - uv.y; gl_Position = vec4(p, 0, 1); }`;
const FS = `#version 300 es
precision highp float; in vec2 uv; out vec4 o;
uniform sampler2D img, hgt; uniform vec2 t; uniform float refract, light; uniform vec3 tint;
void main() {
  float l = texture(hgt, uv - vec2(t.x, 0)).r, r = texture(hgt, uv + vec2(t.x, 0)).r;
  float u = texture(hgt, uv - vec2(0, t.y)).r, d = texture(hgt, uv + vec2(0, t.y)).r;
  vec2 g = vec2(l - r, u - d);
  vec3 c = texture(img, uv + g * refract).rgb;
  vec3 n = normalize(vec3(g * 3., 1.));
  float spec = pow(max(dot(n, normalize(vec3(-.4, -.6, 1.))), 0.), 60.) - pow(max(dot(vec3(0,0,1), normalize(vec3(-.4, -.6, 1.))), 0.), 60.);
  o = vec4(c * (1. + (g.x + g.y) * light) + tint * max(spec, 0.) * .45, 1);
}`;

/** One wave step: writes the next field into `prev` (caller swaps buffers); returns the peak |height|. */
export function stepWave(cur: Float32Array, prev: Float32Array, w: number, h: number, damping: number): number {
  let peak = 0;
  for (let y = 1; y < h - 1; y++)
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x;
      const v = ((cur[i - 1]! + cur[i + 1]! + cur[i - w]! + cur[i + w]!) / 2 - prev[i]!) * damping;
      prev[i] = v;
      const a = v < 0 ? -v : v;
      if (a > peak) peak = a;
    }
  return peak;
}

const reduced = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

export function createWater(canvas: HTMLCanvasElement, opts: WaterOptions = {}): Water {
  const {
    mode = "image", scale = 3, damping = 0.97, hoverRadius = 3, hoverStrength = 0.5,
    clickRadius = 7, clickStrength = 2, refract = 0.012, light = 0.25, tint = [1, 1, 1], idleDrops = null,
  } = opts;
  let source = opts.source ?? null;
  let w = 0, h = 0, cur = new Float32Array(0), prev = new Float32Array(0);
  let running = false, destroyed = false, raf = 0, idleTimer = 0, sized = false, lastInput = 0;
  let last: [number, number] | null = null;
  let draw: () => void = () => {};

  let uploadSource: (() => void) | null = null; // re-upload texture 0 only
  let releaseGl: (() => void) | null = null;

  function glRenderer(): () => void {
    releaseGl?.(); releaseGl = uploadSource = null;
    const gl = canvas.getContext("webgl2", { premultipliedAlpha: false }) as WebGL2RenderingContext | null;
    if (!gl) {
      const c = canvas.getContext("2d");
      return () => { if (c && source) c.drawImage(source as CanvasImageSource, 0, 0, canvas.width, canvas.height); };
    }
    const shaders: WebGLShader[] = [];
    const sh = (type: number, src: string) => {
      const s = gl.createShader(type)!;
      gl.shaderSource(s, src); gl.compileShader(s);
      shaders.push(s);
      return s;
    };
    const pr = gl.createProgram()!;
    for (const s of [sh(gl.VERTEX_SHADER, VS), sh(gl.FRAGMENT_SHADER, FS)]) gl.attachShader(pr, s);
    gl.linkProgram(pr);
    const buf = gl.createBuffer();
    const texs: WebGLTexture[] = [];
    releaseGl = () => {
      for (const t of texs) gl.deleteTexture(t);
      if (buf) gl.deleteBuffer(buf);
      for (const s of shaders) gl.deleteShader(s);
      gl.deleteProgram(pr);
    };
    if (!gl.getProgramParameter(pr, gl.LINK_STATUS) || shaders.some((s) => !gl.getShaderParameter(s, gl.COMPILE_STATUS))) {
      // A 2D context can't be taken from a webgl canvas: hide it so the underlying image shows, unrefracted.
      releaseGl(); releaseGl = null;
      canvas.style.visibility = "hidden";
      return () => {};
    }
    gl.useProgram(pr);
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(pr, "p");
    gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    const tex = (unit: number) => {
      const t = gl.createTexture();
      if (t) texs.push(t);
      gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_2D, t);
      for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR],
        [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]] as [number, number][]) gl.texParameteri(gl.TEXTURE_2D, k, v);
    };
    uploadSource = () => {
      if (!source) return;
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, texs[0]!);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, source as TexImageSource);
    };
    tex(0); uploadSource();
    tex(1); gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    gl.uniform1i(gl.getUniformLocation(pr, "img"), 0);
    gl.uniform1i(gl.getUniformLocation(pr, "hgt"), 1);
    gl.uniform2f(gl.getUniformLocation(pr, "t"), 1 / w, 1 / h);
    gl.uniform3fv(gl.getUniformLocation(pr, "tint"), tint);
    gl.uniform1f(gl.getUniformLocation(pr, "refract"), refract);
    gl.uniform1f(gl.getUniformLocation(pr, "light"), light);
    gl.viewport(0, 0, canvas.width, canvas.height);
    return () => {
      gl.activeTexture(gl.TEXTURE1);
      gl.bindTexture(gl.TEXTURE_2D, texs[1]!);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.R16F, w, h, 0, gl.RED, gl.FLOAT, cur);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    };
  }

  function glassRenderer(): () => void {
    const ctx = canvas.getContext("2d");
    const grid = document.createElement("canvas");
    grid.width = w; grid.height = h;
    const g = grid.getContext("2d");
    if (!ctx || !g) return () => {};
    const out = g.createImageData(w, h), d = out.data;
    return () => {
      for (let y = 1; y < h - 1; y++)
        for (let x = 1; x < w - 1; x++) {
          const i = y * w + x, o = i * 4;
          const s = (cur[i - 1]! - cur[i + 1]! + cur[i - w]! - cur[i + w]!) * light;
          d[o] = d[o + 1] = d[o + 2] = s > 0 ? 255 : 0;
          d[o + 3] = Math.min(1, Math.abs(s)) * (s > 0 ? 255 : 80);
        }
      g.putImageData(out, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.imageSmoothingQuality = "high";
      ctx.drawImage(grid, 0, 0, canvas.width, canvas.height);
    };
  }

  const makeRenderer = () => (mode === "image" ? glRenderer() : glassRenderer());

  function resize() {
    const r = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(r.width * dpr);
    canvas.height = Math.round(r.height * dpr);
    w = Math.max(4, Math.round(r.width / scale));
    h = Math.max(4, Math.round(r.height / scale));
    cur = new Float32Array(w * h); prev = new Float32Array(w * h);
    draw = makeRenderer();
    draw();
  }

  function tick() {
    raf = 0;
    if (destroyed) return;
    const peak = stepWave(cur, prev, w, h, damping);
    [cur, prev] = [prev, cur];
    if (peak > STOP_PEAK) { draw(); raf = requestAnimationFrame(tick); }
    else { running = false; cur.fill(0); prev.fill(0); draw(); } // settle, then idle
  }

  function drop(cx: number, cy: number, radius: number, strength: number) {
    if (destroyed || !w || reduced()) return;
    const x0 = Math.round(cx / scale), y0 = Math.round(cy / scale);
    for (let y = -radius; y <= radius; y++)
      for (let x = -radius; x <= radius; x++) {
        const dd = Math.hypot(x, y);
        if (dd > radius) continue;
        const px = x0 + x, py = y0 + y;
        if (px < 1 || py < 1 || px >= w - 1 || py >= h - 1) continue;
        cur[py * w + px] = cur[py * w + px]! + (strength * (Math.cos((dd / radius) * Math.PI) + 1)) / 2;
      }
    if (!running) { running = true; raf = requestAnimationFrame(tick); }
  }

  const host = canvas.parentElement ?? canvas;
  const at = (e: PointerEvent): [number, number] => {
    const r = canvas.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  };
  const onMove = (e: Event) => {
    lastInput = performance.now();
    const [x, y] = at(e as PointerEvent);
    if (last && Math.hypot(x - last[0], y - last[1]) < scale * 2) return; // trail spacing
    last = [x, y];
    drop(x, y, hoverRadius, hoverStrength);
  };
  const onLeave = () => { last = null; };
  const onDown = (e: Event) => { const [x, y] = at(e as PointerEvent); drop(x, y, clickRadius, clickStrength); };
  const onFocus = () => {
    const r = canvas.getBoundingClientRect();
    drop(r.width / 2, r.height / 2, clickRadius, clickStrength * 0.6);
  };
  host.addEventListener("pointermove", onMove);
  host.addEventListener("pointerleave", onLeave);
  host.addEventListener("pointerdown", onDown);
  host.addEventListener("focusin", onFocus);

  function scheduleIdle() {
    if (!idleDrops) return;
    const [a, b] = idleDrops.every;
    idleTimer = window.setTimeout(() => {
      if (w && performance.now() - lastInput > 2000 && !document.hidden) {
        const r = canvas.getBoundingClientRect();
        drop(r.width * (0.1 + Math.random() * 0.8), r.height * (0.1 + Math.random() * 0.8),
          idleDrops!.radius, idleDrops!.strength * (0.6 + Math.random() * 0.6));
      }
      scheduleIdle();
    }, (a + Math.random() * (b - a)) * 1000);
  }
  scheduleIdle();

  function setSource(img: CanvasImageSource) {
    source = img;
    if (!w) return;
    if (uploadSource) uploadSource(); else draw = makeRenderer();
    draw();
  }

  const ro = typeof ResizeObserver === "function"
    ? new ResizeObserver(() => { if (!sized) { sized = true; resize(); } })
    : null;
  ro?.observe(canvas);

  return {
    drop, setSource,
    destroy() {
      destroyed = true;
      host.removeEventListener("pointermove", onMove);
      host.removeEventListener("pointerleave", onLeave);
      host.removeEventListener("pointerdown", onDown);
      host.removeEventListener("focusin", onFocus);
      if (raf) cancelAnimationFrame(raf);
      clearTimeout(idleTimer);
      ro?.disconnect();
      releaseGl?.(); releaseGl = uploadSource = null;
    },
  };
}
