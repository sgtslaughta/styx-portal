import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, test, expect, vi } from "vitest";

const getTurnCheck = vi.fn();
vi.mock("@/api/client", () => ({ api: { getTurnCheck: () => getTurnCheck() } }));

import { TurnSetupCheck } from "../turn-setup-check";

const resp = {
  provider: "cloudflare",
  checked_at: "2026-11-01T10:00:00Z",
  checks: [
    { id: "turn_credentials", label: "TURN credentials", status: "ok", detail: "Credentials issued with 2 TURN URL(s)." },
    { id: "transport", label: "WebRTC in use", status: "warn", detail: "No workstation uses WebRTC." },
    { id: "analytics", label: "Cloudflare analytics", status: "error", detail: "Analytics token rejected" },
    { id: "x", label: "Other", status: "skip", detail: "Skipped hint" },
  ],
};

const wrap = (provider: string) => render(
  <QueryClientProvider client={new QueryClient()}><TurnSetupCheck provider={provider} /></QueryClientProvider>,
);

describe("TurnSetupCheck", () => {
  test("renders rows with text status and refetches on button", async () => {
    getTurnCheck.mockResolvedValue(resp);
    wrap("cloudflare");
    expect(await screen.findByText("TURN credentials")).toBeTruthy();
    expect(screen.getByText("Analytics token rejected")).toBeTruthy();
    for (const t of ["OK", "Warning", "Error", "Skipped"]) expect(screen.getByText(t)).toBeTruthy();
    expect(getTurnCheck).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: /check setup/i }));
    await waitFor(() => expect(getTurnCheck).toHaveBeenCalledTimes(2));
  });

  test("does not auto-run when provider is none", () => {
    getTurnCheck.mockClear();
    wrap("none");
    expect(getTurnCheck).not.toHaveBeenCalled();
  });
});
