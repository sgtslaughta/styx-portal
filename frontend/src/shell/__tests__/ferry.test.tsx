import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { readPos, snapSide, writePos } from "../ferry-pos";
import { Dock } from "../dock";
import { useHotkey } from "../use-hotkey";

it("snapSide", () => { expect(snapSide(100, 1000)).toBe("left"); expect(snapSide(700, 1000)).toBe("right"); });
it("readPos survives a throwing storage", () => {
  const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("denied"); });
  expect(readPos()).toEqual({ side: "right", y: 0.5 });
  spy.mockRestore();
});
it("writePos/readPos roundtrip", () => { writePos({ side: "left", y: 0.3 }); expect(readPos()).toEqual({ side: "left", y: 0.3 }); });

const tiles = [
  { id: "1", slug: "sonarr", name: "Sonarr", icon: null, mount_mode: "path" as const, enabled: true, up: true, frame_ok: true },
  { id: "2", slug: "immich", name: "Immich", icon: null, mount_mode: "cookie-root" as const, enabled: true, up: null, frame_ok: true },
];
it("lists apps, marks the current one, focus exit only for focus app", () => {
  render(<Dock open onOpenChange={() => {}} tiles={tiles} current="immich" focusSlug="immich" side="right" />);
  expect(screen.getByRole("link", { name: /immich/i })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: /sonarr/i })).toHaveAttribute("href", "/_styx/app/sonarr/");
  expect(screen.getByRole("link", { name: "Exit focus" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("href", "/_styx/exit?next=/");
  expect(screen.getByRole("link", { name: "Pop out" })).toHaveAttribute("target", "_blank");
});
it("no Exit focus when another app holds focus", () => {
  render(<Dock open onOpenChange={() => {}} tiles={tiles} current="sonarr" focusSlug="immich" side="left" />);
  expect(screen.queryByRole("link", { name: "Exit focus" })).toBeNull();
});
it("empty dock says so", () => {
  render(<Dock open onOpenChange={() => {}} tiles={[]} current="x" focusSlug={null} side="right" />);
  expect(screen.getByText("No apps yet")).toBeInTheDocument();
});
it("Esc closes", () => {
  const close = vi.fn();
  render(<Dock open onOpenChange={close} tiles={tiles} current="sonarr" focusSlug={null} side="right" />);
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
  expect(close).toHaveBeenCalledWith(false);
});
it("Alt+Shift+S toggles", () => {
  const toggle = vi.fn();
  function H() { useHotkey(() => [window], toggle); return null; }
  render(<H />);
  fireEvent.keyDown(window, { code: "KeyS", altKey: true, shiftKey: true });
  fireEvent.keyDown(window, { code: "KeyS", altKey: true });
  expect(toggle).toHaveBeenCalledTimes(1);
});
