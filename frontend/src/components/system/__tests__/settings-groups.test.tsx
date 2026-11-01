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

describe("settings group nav", () => {
  test("lists groups, defaults to first, switches on click", async () => {
    wrap();
    const nav = await screen.findByRole("navigation", { name: "Setting groups" });
    expect(nav.querySelectorAll("button").length).toBe(2);
    expect(screen.getByLabelText("GEN_NAME")).toBeTruthy();
    expect(screen.queryByLabelText("SEC_PORT")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Security/ }));
    expect(screen.getByLabelText("SEC_PORT")).toBeTruthy();
    expect(screen.queryByLabelText("GEN_NAME")).toBeNull();
    expect(screen.getByRole("button", { name: /Security/ }).getAttribute("aria-current")).toBe("page");
  });

  test("honours ?group= param", async () => {
    wrap("/?group=security");
    expect(await screen.findByLabelText("SEC_PORT")).toBeTruthy();
    expect(screen.queryByLabelText("GEN_NAME")).toBeNull();
  });

  test("dirty dot appears after editing", async () => {
    wrap();
    const input = await screen.findByLabelText("GEN_NAME");
    expect(screen.queryByTestId("dirty-general")).toBeNull();
    fireEvent.change(input, { target: { value: "b" } });
    expect(screen.getByTestId("dirty-general")).toBeTruthy();
    expect(screen.queryByTestId("dirty-security")).toBeNull();
  });
});
