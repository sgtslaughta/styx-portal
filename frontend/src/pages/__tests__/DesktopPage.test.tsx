import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

const useInstances = vi.fn();
const mutate = vi.fn();
vi.mock("@/hooks/use-instances", () => ({ useInstances: () => useInstances(), useKeepalive: () => ({ mutate }) }));
vi.mock("@/lib/activity", () => ({ startActivityHeartbeat: () => () => {} }));
const useTemplates = vi.fn(() => ({ data: [{ id: "t1", icon: "🌐" }] }));
vi.mock("@/hooks/use-templates", () => ({ useTemplates: () => useTemplates() }));
vi.mock("@/lib/stream-thumb", () => ({ startThumbUploader: () => () => {} }));

import { DesktopPage, faviconHref } from "../DesktopPage";

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
  beforeEach(() => { useInstances.mockReset(); mutate.mockReset(); });

  it("mounts the iframe when running", () => {
    renderAt([inst("running")]);
    const f = screen.getByTitle("My Desk") as HTMLIFrameElement;
    expect(f.getAttribute("src")).toBe("/i/desk/");
    expect(f.hasAttribute("sandbox")).toBe(false);
  });

  it("sets the tab icon from the template and restores it on unmount", () => {
    const link = document.createElement("link");
    link.rel = "icon"; link.href = "http://localhost/favicon.svg";
    document.head.appendChild(link);
    const { unmount } = renderAt([inst("running", { template_id: "t1" })]);
    expect(link.href).toBe(faviconHref("🌐"));
    unmount();
    expect(link.href).toBe("http://localhost/favicon.svg");
    link.remove();
  });

  it("faviconHref passes URLs through", () => {
    expect(faviconHref("/api/x.png")).toBe("/api/x.png");
    expect(faviconHref(null)).toBeNull();
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

  it("shows the idle banner and keeps alive on click", () => {
    renderAt([inst("idle")]);
    expect(screen.getByText(/Pausing soon/)).toBeTruthy();
    fireEvent.click(screen.getByText("I'm here"));
    expect(mutate).toHaveBeenCalledWith("i1", expect.anything());
  });

  it("no banner when running", () => {
    renderAt([inst("running")]);
    expect(screen.queryByText(/Pausing soon/)).toBeNull();
  });
});
