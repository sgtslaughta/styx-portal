import { useRef } from "react";
import { useCanvasEffect } from "@/hooks/use-canvas-effect";
import { createWaves } from "@/lib/effects/waves";

/** Gold wave field + dithered sun with the unfocus-reveal headline. Theme-aware via the .dark class. */
export function LoginBrandPanel() {
  const cv = useRef<HTMLCanvasElement>(null);
  const hero = useRef<HTMLDivElement>(null);
  useCanvasEffect(cv, (c) => createWaves(c, { lines: 28, top: 0.42, calmRect: () => hero.current?.getBoundingClientRect() ?? null }), []);
  return (
    <section className="login-brand">
      <canvas ref={cv} aria-hidden="true" />
      <div ref={hero} className="login-hero reveal">
        <h2>Cross over to your workspaces.</h2>
      </div>
    </section>
  );
}
