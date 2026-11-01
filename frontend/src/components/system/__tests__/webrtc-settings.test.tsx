import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { describe, test, expect, vi, beforeEach } from "vitest";

const getSystemSettings = vi.fn();
const updateSystemSettings = vi.fn();
const resetSystemSetting = vi.fn();
const getTurnUsage = vi.fn();
const updateWorkstation = vi.fn();
vi.mock("@/api/client", () => ({
  api: {
    getSystemSettings: (...a: unknown[]) => getSystemSettings(...a),
    updateSystemSettings: (...a: unknown[]) => updateSystemSettings(...a),
    resetSystemSetting: (...a: unknown[]) => resetSystemSetting(...a),
    getTurnUsage: (...a: unknown[]) => getTurnUsage(...a),
    updateWorkstation: (...a: unknown[]) => updateWorkstation(...a),
  },
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { SystemSettingsPanel } from "../system-settings-panel";
import { estimateCost } from "../turn-cost-card";
import { WorkstationStreamSettings } from "../workstation-stream-settings";
import type { Workstation } from "@/api/client";

const row = (key: string, type: string, value: unknown, extra = {}) => ({
  key, label: key, help: "", type, value, default: value, min: null, max: null, ...extra,
});

function groups(provider: string, isSet = true) {
  return [{
    group: "webrtc", label: "WebRTC / TURN", settings: [
      row("WORKSTATION_TRANSPORT", "enum", "websockets", { choices: ["websockets", "webrtc"] }),
      row("WEBRTC_TURN_PROVIDER", "enum", provider, { choices: ["none", "cloudflare", "generic"] }),
      row("CLOUDFLARE_TURN_TOKEN_ID", "secret", null, { default: "", is_set: isSet }),
      row("CLOUDFLARE_TURN_API_TOKEN", "secret", null, { default: "", is_set: false }),
      row("TURN_HOST", "str", ""),
      row("TURN_PORT", "int", 3478, { min: 1, max: 65535 }),
      row("WEBRTC_MAX_SESSION_H", "int", 8, { min: 0, max: 72 }),
    ],
  }];
}

const usage = {
  month: "2026-11", free_gb: 1000, usd_per_gb: "0.05", total_bytes: 1_234_000_000_000,
  est_usd: 11.7, projected_bytes: 2_000_000_000_000, projected_usd: 50,
  by_workstation: [{ id: "w1", name: "GAME-01", bytes: 5_000_000_000 }],
  by_user: [{ id: "u1", username: "alice", bytes: 5_000_000_000 }],
};

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  updateSystemSettings.mockResolvedValue({});
  getTurnUsage.mockResolvedValue(usage);
});

describe("secret rows", () => {
  test("never render a value, show badge, Clear sends empty string", async () => {
    getSystemSettings.mockResolvedValue(groups("cloudflare"));
    wrap(<SystemSettingsPanel />);
    const input = (await screen.findByLabelText("CLOUDFLARE_TURN_TOKEN_ID")) as HTMLInputElement;
    expect(input.type).toBe("password");
    expect(input.value).toBe("");
    expect(screen.getByText("Set")).toBeTruthy();
    expect(screen.getByText("Not set")).toBeTruthy();
    // only the is_set row has a Clear button
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    await waitFor(() =>
      expect(updateSystemSettings).toHaveBeenCalledWith({ CLOUDFLARE_TURN_TOKEN_ID: "" })
    );
  });

  test("Save sends a newly typed secret", async () => {
    getSystemSettings.mockResolvedValue(groups("cloudflare"));
    wrap(<SystemSettingsPanel />);
    const input = await screen.findByLabelText("CLOUDFLARE_TURN_API_TOKEN");
    fireEvent.change(input, { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(updateSystemSettings).toHaveBeenCalledWith({ CLOUDFLARE_TURN_API_TOKEN: "abc" })
    );
  });
});

describe("provider switch", () => {
  test("shows only fields for the chosen provider", async () => {
    getSystemSettings.mockResolvedValue(groups("none"));
    wrap(<SystemSettingsPanel />);
    await screen.findByLabelText("WEBRTC_MAX_SESSION_H");
    expect(screen.queryByLabelText("TURN_HOST")).toBeNull();
    expect(screen.queryByLabelText("CLOUDFLARE_TURN_TOKEN_ID")).toBeNull();
    fireEvent.change(screen.getByLabelText("WEBRTC_TURN_PROVIDER"), { target: { value: "cloudflare" } });
    expect(screen.getByLabelText("CLOUDFLARE_TURN_TOKEN_ID")).toBeTruthy();
    expect(screen.queryByLabelText("TURN_HOST")).toBeNull();
    fireEvent.change(screen.getByLabelText("WEBRTC_TURN_PROVIDER"), { target: { value: "generic" } });
    expect(screen.getByLabelText("TURN_HOST")).toBeTruthy();
    expect(screen.queryByLabelText("CLOUDFLARE_TURN_TOKEN_ID")).toBeNull();
    expect(screen.getByLabelText("WEBRTC_MAX_SESSION_H")).toBeTruthy();
  });
});

describe("TURN cost card", () => {
  test("what-if math", () => {
    const r = estimateCost(100, 20, 1000, 0.05);
    expect(r.gb).toBeCloseTo(900);
    expect(r.usd).toBe(0);
    const r2 = estimateCost(200, 20, 1000, 0.05);
    expect(r2.gb).toBeCloseTo(1800);
    expect(r2.usd).toBeCloseTo(40);
  });

  test("renders usage", async () => {
    getSystemSettings.mockResolvedValue(groups("none"));
    wrap(<SystemSettingsPanel />);
    expect(await screen.findByText("1234.0 GB")).toBeTruthy();
    expect(screen.getByText("GAME-01")).toBeTruthy();
    expect(screen.getByText("alice")).toBeTruthy();
  });

  test("over budget shows the WebRTC-paused banner and Cloudflare actual", async () => {
    getSystemSettings.mockResolvedValue(groups("none"));
    getTurnUsage.mockResolvedValue({ ...usage, budget_gb: 900, over_budget: true, cf_egress_bytes: 950e9 });
    wrap(<SystemSettingsPanel />);
    expect((await screen.findByRole("alert")).textContent).toMatch(/WebRTC is paused/);
    expect(screen.getByText("Cloudflare actual (egress)")).toBeTruthy();
  });

  test("setup guide explains the Cloudflare steps", async () => {
    getSystemSettings.mockResolvedValue(groups("cloudflare"));
    wrap(<SystemSettingsPanel />);
    fireEvent.click(await screen.findByRole("button", { name: /How to set up WebRTC/ }));
    expect(screen.getByText(/Realtime → TURN Server/)).toBeTruthy();
    expect(screen.getByText(/Account → Account Analytics → Read/)).toBeTruthy();
    expect(screen.queryByText(/static-auth-secret/)).toBeNull();     // coturn steps hidden for cloudflare
  });

  test("error shows usage unavailable", async () => {
    getSystemSettings.mockResolvedValue(groups("none"));
    getTurnUsage.mockRejectedValue(new Error("404"));
    wrap(<SystemSettingsPanel />);
    expect(await screen.findByText("usage unavailable")).toBeTruthy();
  });
});

describe("workstation transport", () => {
  test("saves chosen transport", async () => {
    updateWorkstation.mockResolvedValue({});
    const ws = { id: "w1", stream_settings: {} } as unknown as Workstation;
    render(<WorkstationStreamSettings ws={ws} onSaved={() => {}} />);
    fireEvent.click(screen.getByText("Stream settings"));
    const sel = screen.getByLabelText("Transport") as HTMLSelectElement;
    expect(sel.value).toBe("inherit");
    fireEvent.change(sel, { target: { value: "webrtc" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(updateWorkstation).toHaveBeenCalled());
    expect(updateWorkstation.mock.calls[0]![1].stream_settings.transport).toBe("webrtc");
  });

  test("saves X11 apps (Xwayland) choice", async () => {
    updateWorkstation.mockResolvedValue({});
    const ws = { id: "w1", stream_settings: {} } as unknown as Workstation;
    render(<WorkstationStreamSettings ws={ws} onSaved={() => {}} />);
    fireEvent.click(screen.getByText("Stream settings"));
    const sel = screen.getByLabelText("X11 apps (Xwayland)") as HTMLSelectElement;
    expect(sel.value).toBe("auto");
    expect(screen.getByText(/Lets X11-only apps such as Steam run/)).toBeTruthy();
    fireEvent.change(sel, { target: { value: "off" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(updateWorkstation).toHaveBeenCalled());
    expect(updateWorkstation.mock.calls[0]![1].stream_settings.seat_x11).toBe("off");
  });
});
