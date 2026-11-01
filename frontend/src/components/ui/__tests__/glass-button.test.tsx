import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

vi.mock("@/lib/effects/water", () => ({ createWater: vi.fn(() => ({ destroy() {} })) }));
import { createWater } from "@/lib/effects/water";
import { GlassButton } from "../glass-button";

test("renders label, fires onClick, mounts a glass-mode water canvas", () => {
  const onClick = vi.fn();
  const { container } = render(<GlassButton tone="teal" onClick={onClick}>Resume</GlassButton>);
  fireEvent.click(screen.getByRole("button", { name: "Resume" }));
  expect(onClick).toHaveBeenCalled();
  expect(container.querySelector("button")).toHaveAttribute("data-tone", "teal");
  expect(createWater).toHaveBeenCalledWith(container.querySelector("canvas"), expect.objectContaining({ mode: "glass" }));
});
