import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

import { useRef, useState } from "react";
import type { ServiceTile } from "@/api/client";
import { EdgeTab } from "../edge-tab";

function Harness({ list = tiles }: { list?: ServiceTile[] }) {
  const [open, setOpen] = useState(false);
  const tabRef = useRef<HTMLButtonElement>(null);
  return <>
    <EdgeTab onOpen={() => setOpen(true)} open={open} tabRef={tabRef} />
    <Dock open={open} onOpenChange={setOpen} tiles={list} current="sonarr" focusSlug={null} side="right" tabRef={tabRef} />
  </>;
}
const tabName = "Open the Styx menu (Alt+Shift+S)";

it("click opens the dock; Esc returns focus to the tab", async () => {
  render(<Harness />);
  const tab = screen.getByRole("button", { name: tabName });
  expect(tab).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(tab);
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
  await waitFor(() => expect(document.activeElement).toBe(tab));
});
it("arc offset is capped at 12px for long lists", () => {
  const many: ServiceTile[] = Array.from({ length: 30 }, (_, i) => ({ ...tiles[0], id: `t${i}`, slug: `s${i}`, name: `App ${i}` }));
  const { container } = render(<Dock open onOpenChange={() => {}} tiles={many} current="s0" focusSlug={null} side="right" />);
  void container;
  return waitFor(() => {
    const xs = Array.from(document.querySelectorAll("li")).map((li) => Math.abs(parseFloat(li.style.transform.match(/translateX\((-?[\d.]+)px/)?.[1] ?? "0")));
    expect(xs.length).toBe(30);
    expect(Math.max(...xs)).toBeGreaterThan(5);
    expect(Math.max(...xs)).toBeLessThanOrEqual(12.01);
  });
});
it("hotkey re-attaches after a frame load", () => {
  const toggle = vi.fn();
  const frame = document.createElement("iframe");
  document.body.appendChild(frame);
  let win: Window = frame.contentWindow!;
  function H() { useHotkey(() => [win], toggle, frame); return null; }
  render(<H />);
  const fresh = new EventTarget() as unknown as Window;
  win = fresh;
  frame.dispatchEvent(new Event("load"));
  fresh.dispatchEvent(Object.assign(new Event("keydown"), { code: "KeyS", altKey: true, shiftKey: true }));
  expect(toggle).toHaveBeenCalledTimes(1);
  fresh.dispatchEvent(Object.assign(new Event("keydown"), { code: "KeyS", altKey: true, shiftKey: true, ctrlKey: true }));
  expect(toggle).toHaveBeenCalledTimes(1);
});
