import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, test, expect, vi, beforeEach } from "vitest";
import { toast } from "sonner";
import { ServiceIcon } from "../service-icon";
import { ServiceIconSection } from "../service-icon-section";
import { api, type ProxiedService } from "@/api/client";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("@/api/client", () => ({ api: { setServiceIcon: vi.fn(), refreshServiceIcon: vi.fn() } }));

const svc = (o: Partial<ProxiedService> = {}) =>
  ({ id: "s1", name: "Sonarr", icon_kind: "auto", icon_etag: "e1", ...o }) as ProxiedService;
const set = vi.mocked(api.setServiceIcon);
const refresh = vi.mocked(api.refreshServiceIcon);

beforeEach(() => {
  vi.clearAllMocks();
  set.mockResolvedValue(svc());
  refresh.mockResolvedValue(svc({ icon_kind: "image", icon_etag: "e2" }));
});

describe("ServiceIcon", () => {
  test("img src uses id and etag, decorative", () => {
    const { container } = render(<ServiceIcon s={svc()} />);
    const img = container.querySelector("img")!;
    expect(img.getAttribute("src")).toBe("/api/services/s1/icon?v=e1");
    expect(img.getAttribute("alt")).toBe("");
  });
});

describe("ServiceIconSection", () => {
  test("shows the current icon and saves an emoji through the service endpoint", async () => {
    const onChanged = vi.fn();
    const { container } = render(<ServiceIconSection service={svc()} onChanged={onChanged} />);
    expect(container.querySelector("img")!.getAttribute("src")).toBe("/api/services/s1/icon?v=e1");
    fireEvent.click(screen.getByRole("button", { name: "Emoji" }));
    fireEvent.change(screen.getByLabelText("Emoji"), { target: { value: "📺" } });
    fireEvent.click(screen.getByRole("button", { name: "Save icon" }));
    await waitFor(() => expect(set).toHaveBeenCalledWith("s1", "emoji", "📺"));
    expect(onChanged).toHaveBeenCalled();
  });

  test("refresh button names the service, toasts success and reports the new row", async () => {
    const onChanged = vi.fn();
    render(<ServiceIconSection service={svc()} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Use Sonarr's own icon" }));
    await waitFor(() => expect(refresh).toHaveBeenCalledWith("s1"));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ icon_etag: "e2" }));
  });

  test("refresh failure shows the server message", async () => {
    refresh.mockRejectedValue(new Error("Couldn't find an icon for Sonarr."));
    const onChanged = vi.fn();
    render(<ServiceIconSection service={svc()} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Use Sonarr's own icon" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Couldn't find an icon for Sonarr."));
    expect(onChanged).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Use Sonarr's own icon" })).toBeEnabled();
  });
});
