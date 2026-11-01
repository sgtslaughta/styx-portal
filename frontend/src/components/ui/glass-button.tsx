import { useRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { createWater } from "@/lib/effects/water";
import { useCanvasEffect } from "@/hooks/use-canvas-effect";

interface GlassButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  children: ReactNode;
  /** "light" frosted white (over images); "teal" tinted for flat surfaces. */
  tone?: "light" | "teal";
}

export function GlassButton({ children, onClick, tone = "light", type = "button", ...rest }: GlassButtonProps) {
  const cv = useRef<HTMLCanvasElement>(null);
  useCanvasEffect(cv, (c) => createWater(c, {
    mode: "glass", scale: 2, damping: 0.95, hoverRadius: 6, hoverStrength: 0.9, clickRadius: 10, clickStrength: 3.5, light: 0.7,
  }), []);
  return (
    <button type={type} className="glass" data-tone={tone} onClick={onClick} {...rest}>
      <canvas ref={cv} aria-hidden="true" />
      <span className="lbl">{children}</span>
    </button>
  );
}
