import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, test, vi } from "vitest";

const listUsers = vi.fn();
const adminResetMatrix = vi.fn();
const unlockUser = vi.fn();
const changeRole = vi.fn();
vi.mock("@/api/client", () => ({
  api: {
    listUsers: (...a: unknown[]) => listUsers(...a),
    adminResetMatrix: (...a: unknown[]) => adminResetMatrix(...a),
    unlockUser: (...a: unknown[]) => unlockUser(...a),
    changeRole: (...a: unknown[]) => changeRole(...a),
    getUserGroups: () => Promise.resolve([]),
    listGroups: () => Promise.resolve([]),
  },
  ApiError: class extends Error {},
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("@/components/system/user-groups-dialog", () => ({ UserGroupsDialog: () => null }));

import { UsersPanel } from "../users-panel";

const base = { last_login: null, locked_until: null, failed_count: 0, email: null };
const user = (o: object) => ({ ...base, id: "u1", username: "pat", role: "user", is_active: true, ...o });

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><UsersPanel /></QueryClientProvider>);
}
async function openMenu(name: string) {
  const trigger = await screen.findByRole("button", { name });
  fireEvent.keyDown(trigger, { key: "Enter" });
}

beforeEach(() => vi.clearAllMocks());

describe("UsersPanel table", () => {
  test("Locked filter shows only locked rows and Unlock calls the API", async () => {
    listUsers.mockResolvedValue([
      user({ id: "u1", username: "pat" }),
      user({ id: "u2", username: "theo", locked_until: "2999-01-01T00:00:00Z", failed_count: 5 }),
    ]);
    unlockUser.mockResolvedValue({});
    renderPanel();
    await screen.findByText("pat");
    fireEvent.click(screen.getByRole("button", { name: "Locked 1" }));
    expect(screen.queryByText("pat")).toBeNull();
    expect(screen.getByText("theo")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Unlock" }));
    await waitFor(() => expect(unlockUser).toHaveBeenCalledWith("u2"));
  });

  test("segments show counts", async () => {
    listUsers.mockResolvedValue([user({ role: "admin" }), user({ id: "u2", username: "b" })]);
    renderPanel();
    expect(await screen.findByRole("button", { name: "All 2" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Admins 1" })).toBeTruthy();
  });

  test("inline role select changes role", async () => {
    listUsers.mockResolvedValue([user({})]);
    changeRole.mockResolvedValue({});
    renderPanel();
    fireEvent.change(await screen.findByLabelText("Role for pat"), { target: { value: "admin" } });
    await waitFor(() => expect(changeRole).toHaveBeenCalledWith("u1", "admin"));
  });

  test("More menu keeps groups, profiles, reset, force, disable, delete", async () => {
    listUsers.mockResolvedValue([user({ is_active: false })]);
    renderPanel();
    await openMenu("More actions for pat");
    for (const n of [/Groups/, /Profiles/, /Reset password/, /Force password change/, /Disable/, /Delete permanently/])
      expect(await screen.findByRole("menuitem", { name: n })).toBeTruthy();
  });
});

describe("UsersPanel sign-in card reset", () => {
  test("hidden when the user has no card", async () => {
    listUsers.mockResolvedValue([user({ has_matrix_card: false })]);
    renderPanel();
    await openMenu("More actions for pat");
    await screen.findByRole("menuitem", { name: /Groups/ });
    expect(screen.queryByRole("menuitem", { name: /Reset sign-in card/ })).toBeNull();
  });

  test("confirms, then calls adminResetMatrix", async () => {
    listUsers.mockResolvedValue([user({ has_matrix_card: true })]);
    adminResetMatrix.mockResolvedValue({ ok: true });
    renderPanel();
    await openMenu("More actions for pat");
    fireEvent.click(await screen.findByRole("menuitem", { name: /Reset sign-in card/ }));
    expect(await screen.findByText(/Reset sign-in card\?/)).toBeTruthy();
    expect(adminResetMatrix).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Reset card" }));
    await waitFor(() => expect(adminResetMatrix).toHaveBeenCalledWith("u1"));
  });
});
