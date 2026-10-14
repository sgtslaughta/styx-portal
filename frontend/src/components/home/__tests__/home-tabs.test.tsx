import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { HomeTabs } from "../home-tabs";

const ui = () => render(<HomeTabs workspaces={<p>W-body</p>} apps={<p>A-body</p>} />);
beforeEach(() => { vi.restoreAllMocks(); localStorage.clear(); });

test("defaults to Workspaces; tablist semantics", () => {
  ui();
  expect(screen.getByRole("tablist", { name: "Home" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "Workspaces" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("W-body")).toBeInTheDocument();
});

test("remembers the last tab", () => {
  const { unmount } = ui();
  fireEvent.mouseDown(screen.getByRole("tab", { name: "Apps" }), { button: 0 });
  expect(screen.getByText("A-body")).toBeInTheDocument();
  expect(localStorage.getItem("styx.home.tab")).toBe("apps");
  unmount();
  ui();
  expect(screen.getByRole("tab", { name: "Apps" })).toHaveAttribute("aria-selected", "true");
});

test("arrow keys move between tabs", async () => {
  ui();
  const ws = screen.getByRole("tab", { name: "Workspaces" });
  ws.focus();
  fireEvent.keyDown(ws, { key: "ArrowRight" });
  // Radix moves focus on a deferred tick.
  await waitFor(() => expect(screen.getByRole("tab", { name: "Apps" })).toHaveFocus());
});

test("garbage or throwing storage falls back to Workspaces", () => {
  localStorage.setItem("styx.home.tab", "foo");
  const { unmount } = ui();
  expect(screen.getByRole("tab", { name: "Workspaces" })).toHaveAttribute("aria-selected", "true");
  unmount();
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
  ui();
  fireEvent.mouseDown(screen.getByRole("tab", { name: "Apps" }), { button: 0 });
  expect(screen.getByText("A-body")).toBeInTheDocument();
});
