import { render, screen } from "@testing-library/react";
import { it, expect } from "vitest";
import { IconViewport } from "../icon-viewport";
import type { Instance } from "@/lib/types";

const inst = { id: "i", name: "Box", status: "pulling" } as Instance;

it("shows pull progress as a stepper", () => {
  render(<IconViewport instance={inst} icon="🖥️" pull={{ percent: 30, detail: "Layer 2/5" }} />);
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "30");
  expect(screen.getByText("Layer 2/5")).toBeInTheDocument();
});
it("falls back to a generic pull detail when none is reported", () => {
  render(<IconViewport instance={inst} icon="🖥️" pull={{ percent: 30, detail: null }} />);
  expect(screen.getByText("Pulling image")).toBeInTheDocument();
});
