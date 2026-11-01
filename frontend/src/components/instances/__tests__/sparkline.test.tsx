import { fireEvent, render, screen } from "@testing-library/react";
import { test, expect } from "vitest";
import { OverlaySparkline } from "../sparkline";
import { monotonePath } from "@/lib/chart";

test("monotonePath is smooth and never overshoots", () => {
  const d = monotonePath([[0, 10], [50, 0], [100, 10]]);
  expect(d.startsWith("M0.00,10.00C")).toBe(true);
  const ys = [...d.matchAll(/,(-?\d+\.\d+)/g)].map((m) => Number(m[1]));
  expect(Math.min(...ys)).toBeGreaterThanOrEqual(0);
  expect(monotonePath([])).toBe("");
});

test("accumulates polled values, shows the current value and names the measure on hover", () => {
  const mk = (v: number) => [{ value: v, color: "x", label: "CPU" }];
  const { container, rerender } = render(<OverlaySparkline series={mk(10)} />);
  rerender(<OverlaySparkline series={mk(40)} />);
  expect(screen.getByText("CPU 40%")).toBeTruthy();
  fireEvent.mouseMove(container.querySelector("svg")!, { clientX: 0 });
  expect(screen.getByRole("tooltip").textContent).toContain("CPU 10%");
});
