import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";
const setOpenPrefs = vi.fn();
vi.mock("@/api/client", () => ({ api: {
  me: () => Promise.resolve({ id: "u", username: "alice", email: null, role: "user", open_workspaces: "new_tab", open_apps: null }),
  setOpenPrefs: (p: unknown) => setOpenPrefs(p),
} }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import { OpeningMenu } from "../opening-menu";

test("shows current values incl. Ask, and saves a change", async () => {
  setOpenPrefs.mockResolvedValue({ id: "u", username: "alice", email: null, role: "user", open_workspaces: "new_tab", open_apps: "same_tab" });
  render(<QueryClientProvider client={new QueryClient()}><OpeningMenu username="alice" /></QueryClientProvider>);
  const trigger = screen.getByRole("button", { name: /account menu/i });
  await waitFor(() => expect(trigger).toBeEnabled());
  fireEvent.keyDown(trigger, { key: "Enter" });
  const ws = await screen.findByRole("group", { name: "Workspaces" });
  const apps = screen.getByRole("group", { name: "Apps" });
  expect(within(ws).getByRole("menuitemradio", { name: "New tab" })).toHaveAttribute("aria-checked", "true");
  expect(within(apps).getByRole("menuitemradio", { name: "Ask" })).toHaveAttribute("aria-checked", "true");
  fireEvent.click(within(apps).getByRole("menuitemradio", { name: "This tab" }));
  await waitFor(() => expect(setOpenPrefs).toHaveBeenCalledWith({ open_apps: "same_tab" }));
});

test("Ask saves null", async () => {
  setOpenPrefs.mockResolvedValue({});
  render(<QueryClientProvider client={new QueryClient()}><OpeningMenu username="alice" /></QueryClientProvider>);
  fireEvent.keyDown(screen.getByRole("button", { name: /account menu/i }), { key: "Enter" });
  const ws = await screen.findByRole("group", { name: "Workspaces" });
  fireEvent.click(within(ws).getByRole("menuitemradio", { name: "Ask" }));
  await waitFor(() => expect(setOpenPrefs).toHaveBeenCalledWith({ open_workspaces: null }));
});

test("menu offers Log out and Toggle theme for narrow screens", async () => {
  const onLogout = vi.fn();
  render(<QueryClientProvider client={new QueryClient()}><OpeningMenu username="alice" onLogout={onLogout} onToggleTheme={vi.fn()} /></QueryClientProvider>);
  const trigger = screen.getByRole("button", { name: /account menu/i });
  await waitFor(() => expect(trigger).toBeEnabled());
  fireEvent.keyDown(trigger, { key: "Enter" });
  expect(await screen.findByRole("menuitem", { name: "Toggle theme" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("menuitem", { name: "Log out" }));
  expect(onLogout).toHaveBeenCalled();
});
