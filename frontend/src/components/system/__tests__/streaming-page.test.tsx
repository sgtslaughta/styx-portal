import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, test, expect, vi, beforeEach } from "vitest";

const getSystemSettings = vi.fn();
const updateSystemSettings = vi.fn();
const updateWorkstation = vi.fn();
const listWorkstations = vi.fn();
vi.mock("@/api/client", () => ({
  api: {
    getSystemSettings: (...a: unknown[]) => getSystemSettings(...a),
    updateSystemSettings: (...a: unknown[]) => updateSystemSettings(...a),
    updateWorkstation: (...a: unknown[]) => updateWorkstation(...a),
    listWorkstations: (...a: unknown[]) => listWorkstations(...a),
    getTurnUsage: () => Promise.resolve({ month: "2026-11", free_gb: 1000, usd_per_gb: "0.05", total_bytes: 12.4e9, est_usd: 0, projected_bytes: 31e9, projected_usd: 0, by_workstation: [], by_user: [] }),
    getTurnCheck: () => Promise.resolve({ provider: "cloudflare", checked_at: "2026-11-01T00:00:00Z", checks: [] }),
  },
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { StreamingPage } from "../streaming-page";
import { UnsavedProvider, useUnsaved } from "@/components/settings/unsaved-context";

const row = (key: string, type: string, value: unknown, extra = {}) => ({
  key, label: key, help: "", type, value, default: value, min: null, max: null, ...extra,
});
const ws = (id: string, name: string, ss: Record<string, unknown>, extra = {}) => ({
  id, name, status: "online", in_use: false, in_use_by: null, gpu_info: {}, stream_settings: ss, ...extra,
});

function Count() { const { count } = useUnsaved(); return <output data-testid="count">{count}</output>; }

beforeEach(() => {
  vi.clearAllMocks();
  updateSystemSettings.mockResolvedValue({});
  updateWorkstation.mockResolvedValue({});
  getSystemSettings.mockResolvedValue([{ group: "webrtc", label: "WebRTC", settings: [
    row("WORKSTATION_TRANSPORT", "enum", "webrtc", { choices: ["websockets", "webrtc"] }),
    row("WEBRTC_TURN_PROVIDER", "enum", "cloudflare", { choices: ["none", "cloudflare", "generic"] }),
    row("CLOUDFLARE_TURN_API_TOKEN", "secret", null, { default: "", is_set: true }),
    row("WEBRTC_MAX_SESSION_H", "int", 8, { min: 0, max: 72 }),
  ] }]);
  listWorkstations.mockResolvedValue([
    ws("g", "GAME-01", { encoder: "av1", framerate: 120 }, { in_use: true, in_use_by: "Richard" }),
    ws("m", "mini", {}),
  ]);
});

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><UnsavedProvider><StreamingPage /><Count /></UnsavedProvider></QueryClientProvider>);
}

describe("StreamingPage", () => {
  test("override cells are gold, inherited cells show the default", async () => {
    mount();
    const codec = await screen.findByLabelText("GAME-01 codec") as HTMLSelectElement;
    expect(codec.value).toBe("av1");
    expect(codec.className).toContain("override");
    const conn = screen.getByLabelText("mini connection") as HTMLSelectElement;
    expect(conn.className).not.toContain("override");
    expect(within(conn).getByText("Default (WebRTC)")).toBeTruthy();
    expect(screen.getByText(/Streaming, Richard/)).toBeTruthy();
  });

  test("changing a default segment marks one change", async () => {
    mount();
    await screen.findByLabelText("GAME-01 codec");
    fireEvent.click(within(screen.getByRole("group", { name: "Connection" })).getByText("WebSockets"));
    await waitFor(() => expect(screen.getByTestId("count").textContent).toBe("1"));
  });

  test("workstation edit and default edit save in one click", async () => {
    mount();
    fireEvent.change(await screen.findByLabelText("mini codec"), { target: { value: "hevc" } });
    fireEvent.click(within(screen.getByRole("group", { name: "Connection" })).getByText("WebSockets"));
    await waitFor(() => expect(screen.getByTestId("count").textContent).toBe("2"));
    fireEvent.click(screen.getByText("Save changes"));
    await waitFor(() => expect(updateWorkstation).toHaveBeenCalledWith("m", { stream_settings: { encoder: "hevc" } }));
    expect(updateSystemSettings).toHaveBeenCalledWith({ WORKSTATION_TRANSPORT: "websockets" });
    expect(updateWorkstation).toHaveBeenCalledTimes(1);
  });

  test("replace token stages a secret without showing the old one", async () => {
    mount();
    fireEvent.click(await screen.findByText("Replace token"));
    fireEvent.change(screen.getByLabelText("New API token"), { target: { value: "s3cret" } });
    fireEvent.click(screen.getByText("Use this token"));
    await waitFor(() => expect(screen.getByTestId("count").textContent).toBe("1"));
    fireEvent.click(screen.getByText("Save changes"));
    await waitFor(() => expect(updateSystemSettings).toHaveBeenCalledWith({ CLOUDFLARE_TURN_API_TOKEN: "s3cret" }));
  });
});
