// Water surface: height-field wave sim (two buffers) on the CPU at low res; drawn by
//  - mode "image": a WebGL shader that refracts the source image (thumbnails), sharp at device res;
//  - mode "glass": Canvas2D light glints only (buttons, tiny, CPU is plenty).
// ponytail: one WebGL context per thumbnail; share one context if there are ever >10 on screen.
const reduce = matchMedia("(prefers-reduced-motion: reduce)");

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

function water(canvas, { mode = "image", source = null, scale = 3, damping = 0.97,
  hoverRadius = 3, hoverStrength = 0.5, clickRadius = 7, clickStrength = 2, refract = 0.012, light = 0.25,
  tint = [1, 1, 1], idleDrops = null /* e.g. { every: [1.5, 4], radius: 5, strength: 0.8 } */ } = {}) {
  let w, h, cur, prev, running = false, last = null, draw;

  function resize() {
    const r = canvas.getBoundingClientRect();
    canvas.width = Math.round(r.width * devicePixelRatio); canvas.height = Math.round(r.height * devicePixelRatio);
    w = Math.max(4, Math.round(r.width / scale)); h = Math.max(4, Math.round(r.height / scale));
    cur = new Float32Array(w * h); prev = new Float32Array(w * h);
    draw = mode === "image" ? glRenderer() : glassRenderer();
    draw();
  }

  function glRenderer() {
    const gl = canvas.getContext("webgl2", { premultipliedAlpha: false });
    if (!gl) { const c = canvas.getContext("2d"); return () => c.drawImage(source, 0, 0, canvas.width, canvas.height); } // no WebGL2: static image
    const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return s; };
    const pr = gl.createProgram(); gl.attachShader(pr, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(pr); gl.useProgram(pr);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer()); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(pr, "p"); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    const tex = (unit, filter) => { const t = gl.createTexture(); gl.activeTexture(gl.TEXTURE0 + unit); gl.bindTexture(gl.TEXTURE_2D, t);
      for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, filter], [gl.TEXTURE_MAG_FILTER, filter], [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D, k, v); return t; };
    tex(0, gl.LINEAR); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, source);
    tex(1, gl.LINEAR); gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    gl.uniform1i(gl.getUniformLocation(pr, "img"), 0); gl.uniform1i(gl.getUniformLocation(pr, "hgt"), 1);
    gl.uniform2f(gl.getUniformLocation(pr, "t"), 1 / w, 1 / h);
    gl.uniform3fv(gl.getUniformLocation(pr, "tint"), tint); gl.uniform1f(gl.getUniformLocation(pr, "refract"), refract); gl.uniform1f(gl.getUniformLocation(pr, "light"), light);
    gl.viewport(0, 0, canvas.width, canvas.height);
    return () => { gl.texImage2D(gl.TEXTURE_2D, 0, gl.R16F, w, h, 0, gl.RED, gl.FLOAT, cur); gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4); };
  }

  function glassRenderer() {
    const ctx = canvas.getContext("2d"), grid = document.createElement("canvas"); grid.width = w; grid.height = h;
    const g = grid.getContext("2d"), out = g.createImageData(w, h), d = out.data;
    return () => {
      for (let y = 1; y < h - 1; y++) for (let x = 1; x < w - 1; x++) {
        const i = y * w + x, o = i * 4, s = (cur[i - 1] - cur[i + 1] + cur[i - w] - cur[i + w]) * light;
        d[o] = d[o + 1] = d[o + 2] = s > 0 ? 255 : 0; d[o + 3] = Math.min(1, Math.abs(s)) * (s > 0 ? 255 : 80);
      }
      g.putImageData(out, 0, 0); ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.imageSmoothingQuality = "high"; ctx.drawImage(grid, 0, 0, canvas.width, canvas.height);
    };
  }

  function drop(cx, cy, radius, strength) {
    if (reduce.matches) return;
    const x0 = Math.round(cx / scale), y0 = Math.round(cy / scale);
    for (let y = -radius; y <= radius; y++) for (let x = -radius; x <= radius; x++) {
      const dd = Math.hypot(x, y); if (dd > radius) continue;
      const px = x0 + x, py = y0 + y; if (px < 1 || py < 1 || px >= w - 1 || py >= h - 1) continue;
      cur[py * w + px] += strength * (Math.cos((dd / radius) * Math.PI) + 1) / 2; // smooth bump, no hard edge
    }
    if (!running) { running = true; requestAnimationFrame(tick); }
  }

  function tick() {
    let peak = 0;
    for (let y = 1; y < h - 1; y++) for (let x = 1; x < w - 1; x++) {
      const i = y * w + x, v = ((cur[i - 1] + cur[i + 1] + cur[i - w] + cur[i + w]) / 2 - prev[i]) * damping;
      prev[i] = v; const a = v < 0 ? -v : v; if (a > peak) peak = a;
    }
    [cur, prev] = [prev, cur];
    if (peak > 0.004) { draw(); requestAnimationFrame(tick); } // absolute: small ripples on big canvases keep running
    else { running = false; cur.fill(0); prev.fill(0); draw(); } // settle, then idle: no frames while calm
  }

  const host = canvas.parentElement;
  const at = (e) => { const r = canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  host.addEventListener("pointermove", (e) => {
    const [x, y] = at(e);
    if (last && Math.hypot(x - last[0], y - last[1]) < scale * 2) return; // trail spacing
    last = [x, y]; drop(x, y, hoverRadius, hoverStrength);
  });
  host.addEventListener("pointerleave", () => (last = null));
  host.addEventListener("pointerdown", (e) => { const [x, y] = at(e); drop(x, y, clickRadius, clickStrength); });
  host.addEventListener("focusin", () => { const r = canvas.getBoundingClientRect(); drop(r.width / 2, r.height / 2, clickRadius, clickStrength * 0.6); });
  // Idle: the pool gets an occasional random drop while nobody is touching it.
  let lastInput = 0;
  host.addEventListener("pointermove", () => (lastInput = performance.now()));
  if (idleDrops) (function schedule() {
    const [a, b] = idleDrops.every;
    setTimeout(() => {
      if (w && performance.now() - lastInput > 2000 && !document.hidden) {
        const r = canvas.getBoundingClientRect();
        drop(r.width * (0.1 + Math.random() * 0.8), r.height * (0.1 + Math.random() * 0.8), idleDrops.radius, idleDrops.strength * (0.6 + Math.random() * 0.6));
      }
      schedule();
    }, (a + Math.random() * (b - a)) * 1000);
  })();
  // ponytail: swapping the source rebuilds the GL program (tiny leak per theme switch); keep one program if this becomes frequent.
  function setSource(img) { source = img; if (w) { draw = mode === "image" ? glRenderer() : glassRenderer(); draw(); } }
  let sized = false;
  new ResizeObserver(() => { if (!sized) { sized = true; resize(); } }).observe(canvas); // ponytail: size once; re-init on resize if layouts start changing live
  return { drop, setSource };
}
