import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { TabNav, readHomeTab } from "../tab-nav";

afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); });

test("one main nav: Workspaces, Apps, Templates, Settings", () => {
  render(<TabNav activeTab="apps" onTabChange={vi.fn()} />);
  const nav = screen.getByRole("navigation", { name: "Main" });
  expect(within(nav).getAllByRole("button").map((b) => b.textContent)).toEqual(["Workspaces", "Apps", "Templates", "Settings"]);
  expect(within(nav).getByRole("button", { name: "Apps" })).toHaveAttribute("aria-current", "page");
});

test("Workspaces/Apps are remembered as the landing tab; other tabs are not", () => {
  const onTabChange = vi.fn();
  render(<TabNav activeTab="workspaces" onTabChange={onTabChange} />);
  fireEvent.click(screen.getByRole("button", { name: "Apps" }));
  expect(onTabChange).toHaveBeenCalledWith("apps");
  expect(readHomeTab()).toBe("apps");
  fireEvent.click(screen.getByRole("button", { name: "Templates" }));
  expect(onTabChange).toHaveBeenCalledWith("templates");
  expect(readHomeTab()).toBe("apps");
});

test("garbage or blocked storage lands on Workspaces", () => {
  localStorage.setItem("styx.home.tab", "foo");
  expect(readHomeTab()).toBe("workspaces");
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
  expect(readHomeTab()).toBe("workspaces");
  render(<TabNav activeTab="workspaces" onTabChange={vi.fn()} />);
  expect(() => fireEvent.click(screen.getByRole("button", { name: "Apps" }))).not.toThrow();
});

test("phone: one scrollable row with 44px targets", () => {
  render(<TabNav activeTab="workspaces" onTabChange={vi.fn()} />);
  expect(screen.getByRole("navigation", { name: "Main" }).className).toContain("overflow-x-auto");
  expect(screen.getByRole("button", { name: "Settings" }).className).toContain("max-sm:min-h-11");
});
