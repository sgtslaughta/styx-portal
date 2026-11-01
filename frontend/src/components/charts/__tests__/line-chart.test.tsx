import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { LineChart } from "../line-chart";

const series = [{ name: "CPU", slot: "s1" as const, data: [10, 22, null, 40] }, { name: "Memory", slot: "s2" as const, data: [30, 31, 32, 33] }];

test("tooltip names the series, not 'Value'", () => {
  const { container } = render(<LineChart series={series} labels={["a", "b", "c", "d"]} fmt={(v) => `${v}%`} max={100} />);
  fireEvent.mouseMove(container.querySelector("rect[fill=transparent]")!, { clientX: 272 / 3 });
  const tip = screen.getByRole("tooltip").textContent!;
  expect(tip).toContain("CPU 22%");
  expect(tip).toContain("Memory 31%");
  expect(tip).not.toContain("Value");
});

test("null shows No data in the tooltip and breaks the line", () => {
  const { container } = render(<LineChart series={series} labels={["a", "b", "c", "d"]} fmt={(v) => `${v}%`} max={100} />);
  // CPU: run [0,1] plus lone point 3 (a circle) = 1 path; Memory = 1 path
  expect(container.querySelectorAll("path").length).toBe(2);
  fireEvent.mouseMove(container.querySelector("rect[fill=transparent]")!, { clientX: (2 * 272) / 3 });
  expect(screen.getByRole("tooltip").textContent).toContain("CPU No data");
});
