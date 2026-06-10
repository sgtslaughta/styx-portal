import { useEffect, useRef } from "react";

/**
 * Water-ripple refraction overlay for the login brand panel.
 *
 * A single full-screen WebGL fragment shader reproduces the exact production
 * "river current" line recipe (1px lines @23px/41px, 115deg, drifting, bottom-left
 * masked) and refracts it with faint, randomly-placed "slow drips into a pool".
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
  chroma: 0.02,
  speed: 0.15,
  normScale: 0.05,
} as const;

const VERT = `attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}`;

const FRAG = `#extension GL_OES_standard_derivatives : enable
precision highp float;
uniform vec2 res; uniform float time;
uniform vec4 drips[${MAX_DRIPS}];   // x, y, age, seed
uniform int nd;
uniform float uStrength, uSpec, uCaustic, uChroma, uSpeed, uNorm, uLife;
uniform vec3 uRippleColor;
uniform vec3 uBgDark, uBgLight;

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
// signed distance along the 115deg axis, in px
float axis(vec2 uv){ float a = radians(115.0); return (uv.x * cos(a) - uv.y * sin(a)) * res.x; }
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

  // drift matches the CSS @keyframes flow (set1 ~23px/14s, set2 ~41px/26s)
  float drift1 = time * (23.0 / 14.0), drift2 = time * (41.0 / 26.0);

  float gd = distance(uv, vec2(0.15, 0.0));
  vec3 bg = mix(uBgLight, uBgDark, clamp(gd * 0.95, 0.0, 1.0));

  vec3 c1 = uRippleColor * 0.09;
  vec3 c2 = uRippleColor * 0.06;
  float g1r = axis(uv + off * (1.0 + uChroma)) - drift1;
  float g1g = axis(uv + off) - drift1;
  float g1b = axis(uv + off * (1.0 - uChroma)) - drift1;
  float g2 = axis(uv + off) - drift2;
  vec3 set1 = vec3(lineSet(g1r, 23.0), lineSet(g1g, 23.0), lineSet(g1b, 23.0)) * c1;
  vec3 set2 = lineSet(g2, 41.0) * c2;

  // production bottom-left mask: radial(150% 130% at 0% 100%) #000 30% -> transparent 72%
  float md = distance(uv, vec2(0.0, 1.0));
  float mask = smoothstep(0.72, 0.30, md / 1.3);
  vec3 col = bg + (set1 + set2) * mask;

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
    const uStr = u("uStrength"), uSp = u("uSpec"), uCa = u("uCaustic"), uCh = u("uChroma");
    const uSpd = u("uSpeed"), uNo = u("uNorm"), uLi = u("uLife");
    const uRippleColor = u("uRippleColor");
    const uBgDark = u("uBgDark"), uBgLight = u("uBgLight");

    let w = 0, h = 0;
    const resize = () => {
      const dpr = Math.min(2, window.devicePixelRatio || 1);
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

    // Helper: read CSS custom property and parse as RGB
    const parseRgb = (varName: string): [number, number, number] => {
      const styles = getComputedStyle(canvas);
      const val = styles.getPropertyValue(varName).trim();
      const matches = val.match(/(\d+)/g);
      if (matches && matches.length >= 3) {
        const r = parseInt(matches[0]!, 10);
        const g = parseInt(matches[1]!, 10);
        const b = parseInt(matches[2]!, 10);
        return [r / 255, g / 255, b / 255];
      }
      return [0, 0, 0];
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

      // Read theme-aware ripple color from CSS custom properties
      const [ripR, ripG, ripB] = parseRgb("--brand-ripple-r, var(--brand-ripple-g), var(--brand-ripple-b)");
      // Dark theme: navy to deep navy. Light theme: pale periwinkle to even paler.
      const bgLight = document.documentElement.classList.contains("dark")
        ? [0.039, 0.078, 0.149]
        : [0.965, 0.973, 0.996]; // #f5f9fe -> normalized
      const bgDark = document.documentElement.classList.contains("dark")
        ? [0.020, 0.027, 0.051]
        : [0.929, 0.922, 0.949]; // #ede8f7 -> normalized

      gl.uniform2f(uRes, canvas.width, canvas.height);
      gl.uniform1f(uTime, t);
      gl.uniform4fv(uDrips, arr);
      gl.uniform1i(uNd, drips.length);
      gl.uniform1f(uStr, CFG.strength);
      gl.uniform1f(uSp, CFG.spec);
      gl.uniform1f(uCa, CFG.caustic);
      gl.uniform1f(uCh, CFG.chroma);
      gl.uniform1f(uSpd, CFG.speed);
      gl.uniform1f(uNo, CFG.normScale);
      gl.uniform1f(uLi, CFG.life);
      gl.uniform3f(uRippleColor, ripR, ripG, ripB);
      gl.uniform3fv(uBgDark, bgDark);
      gl.uniform3fv(uBgLight, bgLight);
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
      // otherwise force position:relative; z-index:1 onto this canvas)
      style={{ position: "absolute", zIndex: 0 }}
    />
  );
}
