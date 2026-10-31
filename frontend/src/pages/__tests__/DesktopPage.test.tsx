import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

const useInstances = vi.fn();
vi.mock("@/hooks/use-instances", () => ({ useInstances: () => useInstances() }));
vi.mock("@/lib/stream-thumb", () => ({ startThumbUploader: () => () => {} }));

import { DesktopPage } from "../DesktopPage";

const inst = (status: string, extra = {}) =>
  ({ id: "i1", name: "My Desk", subdomain: "desk", status, ...extra });

function renderAt(list: unknown[] | undefined, pending = false) {
  useInstances.mockReturnValue({ data: list, isPending: pending });
  return render(
    <MemoryRouter initialEntries={["/desktop/desk"]}>
      <Routes><Route path="/desktop/:sub" element={<DesktopPage />} /></Routes>
    </MemoryRouter>,
  );
}

describe("DesktopPage", () => {
  beforeEach(() => useInstances.mockReset());

  it("mounts the iframe when running", () => {
    renderAt([inst("running")]);
    const f = screen.getByTitle("My Desk") as HTMLIFrameElement;
    expect(f.getAttribute("src")).toBe("/i/desk/");
    expect(f.hasAttribute("sandbox")).toBe(false);
  });

  it("does not mount the iframe while starting, shows detail", () => {
    renderAt([inst("pulling", { status_detail: "Pulling 40%" })]);
    expect(screen.queryByTitle("My Desk")).toBeNull();
    expect(screen.getByText("Pulling 40%")).toBeTruthy();
  });

  it("shows not found for an unknown subdomain", () => {
    renderAt([]);
    expect(screen.getByText("Desktop not found")).toBeTruthy();
  });
});
