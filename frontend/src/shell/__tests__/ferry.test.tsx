import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { markDragging, readPos, snapSide, writePos } from "../ferry-pos";
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
  { id: "1", slug: "sonarr", name: "Sonarr", icon: null, mount_mode: "path" as const, enabled: true, up: true, frame_ok: true, needs_setup: false },
  { id: "2", slug: "immich", name: "Immich", icon: null, mount_mode: "cookie-root" as const, enabled: true, up: null, frame_ok: true, needs_setup: false },
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
  const many: ServiceTile[] = Array.from({ length: 30 }, (_, i): ServiceTile => ({ ...(tiles[0] as ServiceTile), id: `t${i}`, slug: `s${i}`, name: `App ${i}` }));
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
it("Escape typed inside the framed app reaches onEscape (the app may hold focus)", () => {
  const onEscape = vi.fn();
  const win = new EventTarget() as unknown as Window;
  function H() { useHotkey(() => [win], vi.fn(), undefined, onEscape); return null; }
  render(<H />);
  win.dispatchEvent(Object.assign(new Event("keydown"), { key: "Escape" }));
  win.dispatchEvent(Object.assign(new Event("keydown"), { key: "a" }));
  expect(onEscape).toHaveBeenCalledTimes(1);
});
const dockProps = { onOpenChange: () => {}, tiles, current: "sonarr", focusSlug: null, side: "right" as const };
it("focus moves into the dock on open and back to the tab on close", async () => {
  const tab = document.createElement("button");
  document.body.appendChild(tab);
  try {
    const props = { ...dockProps, tabRef: { current: tab } };
    const { rerender } = render(<Dock open {...props} />);
    await waitFor(() => expect(screen.getByRole("dialog")).toContainElement(document.activeElement as HTMLElement));
    rerender(<Dock open={false} {...props} />);
    await waitFor(() => expect(tab).toHaveFocus());
  } finally { tab.remove(); }
});
it("opens focused on the current app's link, not the container", async () => {
  render(<Dock open {...dockProps} />);
  await waitFor(() => expect(screen.getByRole("link", { name: /sonarr/i })).toHaveFocus());
});
it("takes focus away from an iframe that held it when the dock opens", async () => {
  const frame = document.createElement("iframe");
  document.body.appendChild(frame);
  try {
    frame.focus();
    expect(document.activeElement).toBe(frame);
    const { rerender } = render(<Dock open={false} {...dockProps} />);
    rerender(<Dock open {...dockProps} />);
    await waitFor(() => expect(screen.getByRole("dialog")).toContainElement(document.activeElement as HTMLElement));
  } finally { frame.remove(); }
});
it("markDragging toggles the body flag the iframe CSS keys on", () => {
  markDragging(true);
  expect(document.body.hasAttribute("data-ferry-drag")).toBe(true);
  markDragging(false);
  expect(document.body.hasAttribute("data-ferry-drag")).toBe(false);
});
it("the edge tab arms the iframe guard on pointer down and releases it on pointer up", () => {
  render(<EdgeTab onOpen={() => {}} />);
  const btn = screen.getByRole("button");
  fireEvent.pointerDown(btn);
  expect(document.body.hasAttribute("data-ferry-drag")).toBe(true);
  fireEvent.pointerUp(window);
  expect(document.body.hasAttribute("data-ferry-drag")).toBe(false);
});
it("renders an emoji icon as text, never as an img src", () => {
  const t = tiles.slice(0, 1).map((x) => ({ ...x, icon: "🎬" }));
  const { baseElement } = render(<Dock open onOpenChange={() => {}} tiles={t} current="x" focusSlug={null} side="right" />);
  expect(baseElement.querySelector("img")).toBeNull();
  expect(screen.getByText("🎬")).toBeInTheDocument();
});
