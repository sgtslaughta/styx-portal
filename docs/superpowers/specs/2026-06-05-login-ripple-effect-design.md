# Login Brand Panel — Water Ripple Refraction Effect

**Date:** 2026-06-05
**Status:** Approved (validated via live visual companion, v1→v4)
**Area:** `frontend/src/components/auth/LoginBrandPanel.tsx`

## Goal

Add a gentle, random "slow drips into a pool" water effect over the existing
angled-line "river current" backdrop on the login page's left brand panel. The
base design must be preserved exactly; the ripple is a faint enhancement.

## Decision: raw WebGL, zero dependencies

`pixi.js` / `pixel.js` rejected — a ~450KB WebGL lib is dead weight for one
subtle panel effect. The whole effect is a single full-screen fragment shader
(~140 lines). No new npm dependencies.

## Visual spec (locked from v4)

The shader reproduces the **exact** production line recipe, then refracts it:

- Background: `radial-gradient(140% 120% at 15% 100%, #0a1426, #070a12 45%, #05070d)`
- Line set 1: 1px lines every 23px, `rgba(70,140,255,.09)`, 115°
- Line set 2: 1px lines every 41px, `rgba(40,90,200,.06)`, 115°
- Drift: set1 ~23px/14s, set2 ~41px/26s (matches CSS `@keyframes flow`)
- Bottom-left visibility mask: `radial(150% 130% at 0% 100%, #000 30% → transparent 72%)`

Ripple (deliberately faint, final tuned values):

| Param | Value | Meaning |
|-------|-------|---------|
| `strength` | 0.004 | refraction displacement of lines |
| `spec` | 0.2 | specular crest brightness |
| `caustic` | 0.05 | crest brightening |
| `chroma` | 0.02 | R/G/B split on displacement |
| `speed` | 0.15 | wavefront expansion (uv/s) |
| `normScale` | 0.05 | surface-normal slope scale |
| `life` | 6.0 s | drip lifetime |

### Physics

Each drip contributes a height term `h(r,age)`:
- wave train `sin(r·110 − age·omega + seed)`, `omega = 110·speed`
- `distDecay = exp(-r·4.5)`, `timeDecay = exp(-age·0.6)`
- `edge = smoothstep(front, front-0.06, r)` — no disturbance ahead of wavefront
- `lifeFade = 1 − smoothstep(life-1.2, life, age)` — eases to **exactly 0** before
  the drip is culled (no pop)

Surface normal via finite difference of total height `H(q)` (3 samples/pixel) →
drives refraction offset, specular, caustics. All ripple lighting is multiplied
by the same bottom-left mask as the lines.

### Drip scheduler (JS)

- Random placement across the **whole** panel (`x` full width, `y` 0.08–0.96)
- Slow cadence: next drip in 3.0–7.0 s
- Hard cap: `minGap = 0.5 s` → never more than **2 drips/second**
- Max 8 concurrent drips (fixed-size uniform array)

## Component design

New file `frontend/src/components/auth/RippleCanvas.tsx`:

- Visual-only, no props. Renders a single `<canvas>` absolutely positioned
  inside `.styx-brand` at `z-index:1` (below content at `z-index:2`).
- Owns: WebGL init, shader compile (with `OES_standard_derivatives` for
  `fwidth`), drip scheduler, render loop, resize handling.
- Cleanup on unmount: `cancelAnimationFrame`, `loseContext()`.

`LoginBrandPanel.tsx` mounts `<RippleCanvas />` inside the existing `.styx-brand`
div. Because the canvas is **opaque** and covers the panel, it naturally hides
the CSS `::before/::after` line layers when active — no doubling.

### Graceful degradation (CSS base always survives)

`RippleCanvas` returns `null` (renders nothing) when:
- `prefers-reduced-motion: reduce`, or
- WebGL context unavailable / shader fails to compile

In those cases the canvas is absent, so the existing CSS gradient + animated
line layers show through unchanged. The base design is never lost.

## Testing

Repo frontend tests use `node:test` (no DOM/WebGL). This effect cannot be
meaningfully unit-tested there. Verification:
- `npm run lint` (`tsc --noEmit`) must pass.
- Manual: effect renders over lines; reduced-motion shows static CSS base.

## Out of scope

- Touch/click interaction (explicitly removed per feedback)
- Any change to auth logic, layout, or copy
- A pixi.js / external animation dependency
