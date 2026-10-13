import { render, screen } from "@testing-library/react";
import { it, expect } from "vitest";
import { Stepper } from "@/components/ui/stepper";
const steps = [
  { id: "a", label: "Back up settings", state: "done" as const },
  { id: "b", label: "Apply base path", state: "active" as const, percent: 40, detail: "Writing config.xml" },
  { id: "c", label: "Restart app", state: "failed" as const, detail: "Timed out" },
  { id: "d", label: "Check it answers", state: "skipped" as const },
];
it("renders an ordered list with states", () => {
  render(<Stepper steps={steps} />);
  const items = screen.getAllByRole("listitem");
  expect(items).toHaveLength(4);
  expect(items[1]).toHaveAttribute("aria-current", "step");
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "40");
  expect(screen.getByText("Timed out")).toBeInTheDocument();
  expect(items[0]).toHaveTextContent(/done/i);
});
it("shows the percent as text and aria-valuetext while active", () => {
  render(<Stepper steps={steps} />);
  expect(screen.getByText("40%")).toBeInTheDocument();
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "40%");
});
