import { readFileSync } from "node:fs";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "./ThemeProvider";

const mq = { matches: false, addEventListener() {}, removeEventListener() {} };
beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("matchMedia", () => mq);
  vi.useFakeTimers({ toFake: ["requestAnimationFrame", "cancelAnimationFrame"] });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  document.documentElement.className = "";
});

describe("theme switch", () => {
  it("suppresses transitions while .dark flips, then restores them", () => {
    localStorage.setItem("theme", "dark");
    render(<MemoryRouter initialEntries={["/"]}><ThemeProvider>x</ThemeProvider></MemoryRouter>);
    const root = document.documentElement;
    expect(root.classList.contains("dark")).toBe(true);
    expect(root.classList.contains("no-transitions")).toBe(true);
    vi.advanceTimersByTime(100);
    expect(root.classList.contains("no-transitions")).toBe(false);
  });
});

describe("reduced motion", () => {
  const css = readFileSync("src/styles/globals.css", "utf8");
  it("css kills animation and transition under prefers-reduced-motion", () => {
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\)\s*\{[^}]*animation-duration:\s*1ms !important/);
    expect(css).toMatch(/\.no-transitions \*/);
  });
  it("framer-motion honours the user setting app-wide", () => {
    expect(readFileSync("src/main.tsx", "utf8")).toContain('<MotionConfig reducedMotion="user">');
  });
});
