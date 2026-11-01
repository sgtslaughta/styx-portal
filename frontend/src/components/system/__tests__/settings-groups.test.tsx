import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { describe, test, expect, vi, beforeEach } from "vitest";

const getSystemSettings = vi.fn();
vi.mock("@/api/client", () => ({
  api: {
    getSystemSettings: (...a: unknown[]) => getSystemSettings(...a),
    updateSystemSettings: vi.fn(),
    resetSystemSetting: vi.fn(),
    getTurnUsage: vi.fn().mockResolvedValue({}),
  },
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { SystemSettingsPanel } from "../system-settings-panel";

const row = (key: string, type: string, value: unknown) => ({
  key, label: key, help: "", type, value, default: value, min: null, max: null,
});
const data = [
  { group: "general", label: "General", settings: [row("GEN_NAME", "str", "a")] },
  { group: "security", label: "Security", settings: [row("SEC_PORT", "int", 5)] },
];

function wrap(url = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}>
        <SystemSettingsPanel />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => getSystemSettings.mockResolvedValue(data));

describe("settings groups", () => {
  test("renders every group as a card in one grid", async () => {
    wrap();
    expect(await screen.findByLabelText("GEN_NAME")).toBeTruthy();
    expect(screen.getByLabelText("SEC_PORT")).toBeTruthy();
    expect(document.querySelectorAll("fieldset.grp").length).toBe(2);
  });

  test("editing shows the save pill; Discard clears it", async () => {
    wrap();
    fireEvent.change(await screen.findByLabelText("GEN_NAME"), { target: { value: "b" } });
    expect(screen.getByText(/unsaved change$/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    expect(screen.queryByTestId("save-pill")).toBeNull();
  });
});

describe("settings grid", () => {
  test("groups sit in the auto-fill grid; guide and cost span all columns", async () => {
    getSystemSettings.mockResolvedValue([
      { group: "webrtc", label: "WebRTC", settings: [row("WEBRTC_TURN_PROVIDER", "str", "none")] },
    ]);
    wrap();
    const grid = await screen.findByTestId("settings-grid");
    expect(grid.className).toMatch(/groups/);
    expect(screen.getByTestId("turn-guide-wrap").className).toMatch(/col-span-full/);
    expect(screen.getByTestId("turn-cost-wrap").className).toMatch(/col-span-full/);
  });
});
