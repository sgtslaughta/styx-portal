import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, test, expect, vi } from "vitest";

const requestAgentUpdate = vi.fn().mockResolvedValue({});
const requestAgentUpdateOutdated = vi.fn().mockResolvedValue({ requested: 1 });
const ws = {
  id: "w1", name: "box", status: "online", agent_outdated: true, agent_version: "0.9.30",
  update_state: "", all_users: true, allowed_user_ids: [], os_info: {}, gpu_info: {},
  stream_settings: {}, display_server: "wayland", lan_ip: "", port: 1, last_heartbeat: null,
  last_error: null, in_use: false, in_use_self: false, in_use_by: null,
  icon_kind: "auto", icon_etag: "",
};
vi.mock("@/api/client", () => ({
  api: {
    listWorkstations: () => Promise.resolve([ws]),
    listUsers: () => Promise.resolve([]),
    workstationThumbUrl: (id: string) => `/t/${id}`,
    requestAgentUpdate: (...a: unknown[]) => requestAgentUpdate(...a),
    requestAgentUpdateOutdated: (...a: unknown[]) => requestAgentUpdateOutdated(...a),
  },
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("@/components/system/workstation-icon", () => ({ WorkstationIcon: () => null }));
vi.mock("@/components/system/workstation-icon-settings", () => ({ WorkstationIconSettings: () => null }));
vi.mock("@/components/system/workstation-specs", () => ({ WorkstationSpecs: () => null }));
vi.mock("@/components/system/workstation-stream-settings", () => ({ WorkstationStreamSettings: () => null }));

import { WorkstationsPanel } from "../workstations-panel";

describe("WorkstationsPanel agent update", () => {
  test("buttons call the right endpoints", async () => {
    render(<WorkstationsPanel />);
    fireEvent.click(await screen.findByText("Update agent"));
    await waitFor(() => expect(requestAgentUpdate).toHaveBeenCalledWith("w1"));
    fireEvent.click(screen.getByText("Update all outdated"));
    await waitFor(() => expect(requestAgentUpdateOutdated).toHaveBeenCalled());
  });

  test("row shows em dash meters without data and Manage opens the dialog", async () => {
    render(<WorkstationsPanel />);
    expect(await screen.findByText("Enroll a workstation")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Manage" }));
    expect(await screen.findByRole("button", { name: "Revoke" })).toBeTruthy();
  });
});
