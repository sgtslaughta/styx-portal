import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { Frame } from "../frame";

const tile = { id: "1", slug: "sonarr", name: "Sonarr", icon: null, mount_mode: "path", enabled: true, up: true, frame_ok: true } as const;

it("shows the fallback when the frame refuses to load", () => {
  const { container } = render(<Frame tile={tile} inner="/" onTitle={() => {}} />);
  const iframe = container.querySelector("iframe")!;
  Object.defineProperty(iframe, "contentWindow", { get() { throw new DOMException("x", "SecurityError"); } });
  fireEvent.load(iframe);
  expect(screen.getByRole("heading", { name: "Sonarr can't run inside Styx" })).toBeTruthy();
  expect(screen.getByRole("link", { name: "Open Sonarr on its own" }).getAttribute("href")).toBe("/sonarr/");
});
