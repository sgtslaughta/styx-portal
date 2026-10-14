import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, test, vi } from "vitest";

const listUsers = vi.fn();
vi.mock("@/api/client", () => ({
  api: { listUsers: (...a: unknown[]) => listUsers(...a) },
  ApiError: class extends Error {},
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("@/components/system/user-groups-dialog", () => ({ UserGroupsDialog: () => null }));

import { UsersPanel } from "../users-panel";

const base = { last_login: null, locked_until: null };
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

describe("UsersPanel row actions at small widths", () => {
  test("role, unlock and role-change live in the More menu with mobile-only items", async () => {
    listUsers.mockResolvedValue([user({ locked_until: "2999-01-01T00:00:00Z" })]);
    renderPanel();
    await openMenu("More actions for pat");
    const adminItem = await screen.findByRole("menuitem", { name: /Make admin/ });
    expect(adminItem.className).toContain("sm:hidden");
    const unlockItem = screen.getByRole("menuitem", { name: /Unlock/ });
    expect(unlockItem.className).toContain("sm:hidden");
    expect(screen.getByRole("menuitem", { name: /Groups/ })).toBeTruthy();
  });

  test("inactive users still get the menu", async () => {
    listUsers.mockResolvedValue([user({ is_active: false })]);
    renderPanel();
    await openMenu("More actions for pat");
    expect(await screen.findByRole("menuitem", { name: /Groups/ })).toBeTruthy();
    expect(screen.queryByRole("menuitem", { name: /Make admin/ })).toBeNull();
  });

  test("role shows under the username on mobile", async () => {
    listUsers.mockResolvedValue([user({ role: "admin" })]);
    renderPanel();
    await waitFor(() => expect(screen.getAllByText("admin").some((e) => e.className.includes("sm:hidden"))).toBe(true));
  });
});
