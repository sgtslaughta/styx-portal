import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Sparkline } from "../sparkline";

test("empty data renders No data yet", () => {
  render(<Sparkline data={[]} name="CPU" />);
  expect(screen.getByText("No data yet")).toBeTruthy();
});

test("all-null data renders No data yet", () => {
  render(<Sparkline data={[null, null]} name="CPU" />);
  expect(screen.getByText("No data yet")).toBeTruthy();
});

test("null breaks the line and hover names the measure", () => {
  const { container } = render(<Sparkline data={[10, 20, null, 30, 40]} name="CPU" fmt={(v) => `${v}%`} />);
  expect(container.querySelectorAll('path[stroke]').length).toBe(2);
  fireEvent.mouseMove(container.querySelector("svg")!, { clientX: 0 });
  expect(screen.getByRole("tooltip").textContent).toContain("CPU 10%");
});
