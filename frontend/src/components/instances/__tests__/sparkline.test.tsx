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

test("renders gradient area + curve and shows hover tooltip", () => {
  const mk = (v: number) => [{ value: v, color: "var(--chart-1)", label: "CPU" }];
  const { container, rerender } = render(<OverlaySparkline series={mk(10)} />);
  rerender(<OverlaySparkline series={mk(40)} />);
  expect(container.querySelectorAll("linearGradient").length).toBe(1);
  expect(container.querySelectorAll("path").length).toBe(2);
  expect(screen.getByText("CPU 40%")).toBeTruthy();
  expect(screen.queryByRole("tooltip")).toBeNull();
  const root = container.firstElementChild!;
  root.getBoundingClientRect = () => ({ left: 0, width: 100 }) as DOMRect;
  fireEvent.mouseMove(root, { clientX: 0 });
  expect(screen.getByRole("tooltip").textContent).toBe("CPU 10%");
});
