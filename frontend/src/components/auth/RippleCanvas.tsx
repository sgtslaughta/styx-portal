import { useEffect, useRef } from "react";

/**
 * Water-ripple refraction overlay for the login brand panel.
 *
 * A single full-screen WebGL fragment shader renders the panel's diagonal
 * gradient plus the "river current" line recipe (1px lines @23px/41px CSS px,
 * 115deg, drifting, bottom-left masked) and refracts the lines with faint,
 * randomly-placed "slow drips into a pool". The CSS ::before/::after line
 * layers sit at z:-1 as a no-WebGL fallback; this opaque canvas covers them.
 *
 * Theme-aware: reads ripple color from --brand-ripple-r/g/b CSS custom properties,
 * allowing light/dark theme variants with distinct visual character.
 *
 * Zero dependencies. Visual only — no props, no logic.
 *
 * Graceful degradation: if WebGL is unavailable, the shader fails to compile, or
 * the user prefers reduced motion, nothing is drawn and the canvas stays
 * transparent — the existing CSS line layers beneath show through unchanged.
 */

const MAX_DRIPS = 8;

// Tuned final values (see docs/superpowers/specs/2026-06-05-login-ripple-effect-design.md)
const CFG = {
  rateMin: 3.0,
  rateMax: 7.0,
  minGap: 0.5, // hard cap: max 2 drips/second
  life: 6.0,
  strength: 0.004,
  spec: 0.2,
  caustic: 0.05,
  speed: 0.15,
  normScale: 0.05,
} as const;

const VERT = `attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}`;

const FRAG = `#extension GL_OES_standard_derivatives : enable
precision highp float;
uniform vec2 res; uniform float time; uniform float uDpr;
uniform vec4 drips[${MAX_DRIPS}];   // x, y, age, seed
uniform int nd;
uniform float uStrength, uSpec, uCaustic, uSpeed, uNorm, uLife;
uniform float uLineAlpha;
uniform vec3 uRippleColor;
uniform vec3 uBgNear, uBgFar;   // near = upper-right corner, far = lower-left

float dripH(vec2 q, vec4 d){
  vec2 c = d.xy; float age = d.z;
  float r = length(q - c);
  float front = uSpeed * age;
  if (r > front) return 0.0;
  float k = 110.0; float omega = k * uSpeed;
  float wave = sin(r * k - age * omega + d.w * 6.28);
  float distDecay = exp(-r * 4.5);
  float timeDecay = exp(-age * 0.6);
  float edge = smoothstep(front, front - 0.06, r);
  float lifeFade = 1.0 - smoothstep(uLife - 1.2, uLife, age); // -> exactly 0 at end
  return wave * distDecay * timeDecay * edge * lifeFade;
}
float H(vec2 q){
  float h = 0.0;
  for (int i = 0; i < ${MAX_DRIPS}; i++){ if (i >= nd) break; h += dripH(q, drips[i]); }
  return h;
}
// signed distance along the CSS 115deg gradient axis, in CSS px.
// Scales x/y by their own resolution (not res.x for both) so the line angle
// matches the CSS layers at any panel aspect ratio.
float axis(vec2 uv){
  float a = radians(115.0);
  return (uv.x * res.x * sin(a) + uv.y * res.y * cos(a)) / uDpr;
}
#define PERIOD 26.0
// coverage of a 1px line in the last 1px of each P-px period
float lineSet(float g, float P){
  float f = mod(g, P);
  float aa = fwidth(g) + 0.5;
  return smoothstep(P - 1.0 - aa, P - 1.0, f) * (1.0 - step(P, f));
}
void main(){
  vec2 uv = gl_FragCoord.xy / res.xy;
  vec2 q = uv; q.x *= res.x / res.y;
  float e = 2.0 / res.y;
  float h = H(q), hx = H(q + vec2(e, 0.0)), hy = H(q + vec2(0.0, e));
  vec2 grad = vec2(hx - h, hy - h) / e;
  vec3 n = normalize(vec3(-grad * uNorm, 1.0));
  vec2 off = grad * uStrength;

  // diagonal gradient: smooth full-diagonal blend from far (lower-left) to near
  // (upper-right). smoothstep eases both ends so there's no hard hold or kink —
  // the transition is stretched across the entire panel. (matches .styx-brand CSS)
  float t = smoothstep(0.0, 2.0, uv.x + uv.y);
  vec3 bg = mix(uBgFar, uBgNear, t);

  // ONE uniform line set, evenly spaced, refracted by the drip gradient.
  // (A second set at a different period/drift produced overlapping moiré.)
  float drift1 = time * (PERIOD / 14.0);
  float g = axis(uv + off) - drift1;
  float cover = lineSet(g, PERIOD);

  // bottom-left mask. WebGL origin is bottom-left, so the lower-left corner is
  // uv=(0,0) — the CSS 'at 0% 100%' anchor flips to y=0 here.
  float md = distance(uv, vec2(0.0, 0.0));
  float mask = smoothstep(0.95, 0.18, md);
  // mix (not add) toward line color so dark lines stay dark on light bg
  vec3 col = mix(bg, uRippleColor, clamp(cover, 0.0, 1.0) * uLineAlpha * mask);

  // Upper-right band of the SAME line field (same axis/period/phase, so it is
  // collinear with the bottom set and lines up perfectly), angled '/' toward
  // the lower-left. Anchored upper-right, dark navy for contrast.
  float md2 = distance(uv, vec2(1.0, 1.0));
  float mask2 = smoothstep(0.95, 0.18, md2);
  vec3 darkBlue = vec3(0.043, 0.078, 0.255); // #0b1441
  col = mix(col, darkBlue, clamp(cover, 0.0, 1.0) * (uLineAlpha + 0.18) * mask2);

  vec3 lightDir = normalize(vec3(-0.4, 0.5, 0.8));
  float spec = pow(max(dot(n, lightDir), 0.0), 24.0) * uSpec;
  col += vec3(0.7, 0.85, 1.0) * spec * 0.3 * mask;
  col += uRippleColor * max(h, 0.0) * uCaustic * mask;

  gl_FragColor = vec4(col, 1.0);
}`;

function compile(gl: WebGLRenderingContext, type: number, src: string): WebGLShader | null {
  const s = gl.createShader(type);
  if (!s) return null;
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
    console.error("RippleCanvas shader:", gl.getShaderInfoLog(s));
    gl.deleteShader(s);
    return null;
  }
  return s;
}

interface Drip {
  x: number;
  y: number;
  t0: number;
  seed: number;
}

export function RippleCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const gl = canvas.getContext("webgl", { alpha: true, antialias: true });
    if (!gl) return;
    gl.getExtension("OES_standard_derivatives");

    const vs = compile(gl, gl.VERTEX_SHADER, VERT);
    const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) return;
    const prog = gl.createProgram();
    if (!prog) return;
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      console.error("RippleCanvas link:", gl.getProgramInfoLog(prog));
      return;
    }
    gl.useProgram(prog);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const pl = gl.getAttribLocation(prog, "p");
    gl.enableVertexAttribArray(pl);
    gl.vertexAttribPointer(pl, 2, gl.FLOAT, false, 0, 0);

    const u = (name: string) => gl.getUniformLocation(prog, name);
    const uRes = u("res"), uTime = u("time"), uDrips = u("drips"), uNd = u("nd");
    const uStr = u("uStrength"), uSp = u("uSpec"), uCa = u("uCaustic");
    const uSpd = u("uSpeed"), uNo = u("uNorm"), uLi = u("uLife"), uDprLoc = u("uDpr");
    const uRippleColor = u("uRippleColor"), uLineAlpha = u("uLineAlpha");
    const uBgNear = u("uBgNear"), uBgFar = u("uBgFar");

    let w = 0, h = 0, dpr = 1;
    const resize = () => {
      dpr = Math.min(2, window.devicePixelRatio || 1);
      const r = canvas.getBoundingClientRect();
      w = r.width; h = r.height;
      canvas.width = Math.max(1, Math.round(w * dpr));
      canvas.height = Math.max(1, Math.round(h * dpr));
      gl.viewport(0, 0, canvas.width, canvas.height);
    };
    resize();
    window.addEventListener("resize", resize);

    let start = 0, next = 0, last = -99, seed = 0.1, raf = 0;
    let drips: Drip[] = [];
    const arr = new Float32Array(MAX_DRIPS * 4);

    // Helper: read the three --brand-ripple-* custom properties as normalized RGB
    const parseRgb = (): [number, number, number] => {
      const styles = getComputedStyle(canvas);
      const chan = (name: string) =>
        (parseInt(styles.getPropertyValue(name).trim(), 10) || 0) / 255;
      return [chan("--brand-ripple-r"), chan("--brand-ripple-g"), chan("--brand-ripple-b")];
    };

    const frame = (now: number) => {
      if (!start) start = now;
      const t = (now - start) / 1000;
      if (t > next && t - last >= CFG.minGap) {
        next = t + CFG.rateMin + Math.random() * (CFG.rateMax - CFG.rateMin);
        last = t;
        seed = (seed + 0.37) % 1;
        drips.push({ x: (Math.random() * w) / h, y: 0.08 + Math.random() * 0.88, t0: t, seed });
      }
      drips = drips.filter((d) => t - d.t0 < CFG.life).slice(-MAX_DRIPS);
      arr.fill(0);
      drips.forEach((d, i) => {
        arr[i * 4] = d.x;
        arr[i * 4 + 1] = d.y;
        arr[i * 4 + 2] = t - d.t0;
        arr[i * 4 + 3] = d.seed;
      });

      // Read theme-aware line color from CSS custom properties
      const [ripR, ripG, ripB] = parseRgb();
      const isDark = document.documentElement.classList.contains("dark");
      // Gradient anchored upper-right (must match the .styx-brand CSS gradient):
      // dark theme: royal blue #2440a6 -> deep navy #04081a
      // light theme: royal blue #233e9c -> off-white #faf8f3
      const bgNear = isDark
        ? [0.141, 0.251, 0.651]
        : [0.137, 0.243, 0.612];
      const bgFar = isDark
        ? [0.016, 0.031, 0.102]
        : [0.980, 0.973, 0.953];
      const lineAlpha = isDark ? 0.52 : 0.44;

      gl.uniform2f(uRes, canvas.width, canvas.height);
      gl.uniform1f(uTime, t);
      gl.uniform4fv(uDrips, arr);
      gl.uniform1i(uNd, drips.length);
      gl.uniform1f(uStr, CFG.strength);
      gl.uniform1f(uSp, CFG.spec);
      gl.uniform1f(uCa, CFG.caustic);
      gl.uniform1f(uSpd, CFG.speed);
      gl.uniform1f(uDprLoc, dpr);
      gl.uniform1f(uNo, CFG.normScale);
      gl.uniform1f(uLi, CFG.life);
      gl.uniform3f(uRippleColor, ripR, ripG, ripB);
      gl.uniform1f(uLineAlpha, lineAlpha);
      gl.uniform3fv(uBgNear, bgNear);
      gl.uniform3fv(uBgFar, bgFar);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      gl.getExtension("WEBGL_lose_context")?.loseContext();
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none inset-0 h-full w-full"
      // inline position/z-index beat the `.styx-brand > *` rule (which would
      // otherwise force position:relative; z-index:1 onto this canvas).
      // z:0 paints above the z:-1 CSS line layers (no-WebGL fallback) so only
      // one line system is ever visible.
      style={{ position: "absolute", zIndex: 0 }}
    />
  );
}
