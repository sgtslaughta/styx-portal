import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

const { deleteInstance, listTemplates } = vi.hoisted(() => ({
  deleteInstance: vi.fn(), listTemplates: vi.fn(),
}));
vi.mock("@/api/client", () => ({ api: { deleteInstance, listTemplates } }));
vi.mock("@/components/open-prompt", () => ({ useOpenChoice: () => vi.fn() }));
import { ActionBar } from "../action-bar";
import type { Instance } from "@/lib/types";

const mk = (extra: Partial<Instance>) =>
  ({ id: "i1", template_id: "t1", name: "Desk", subdomain: "desk", status: "stopped", ...extra }) as Instance;

function open(inst: Instance) {
  render(<QueryClientProvider client={new QueryClient()}><ActionBar instance={inst} /></QueryClientProvider>);
  fireEvent.click(screen.getByRole("button", { name: /destroy/i }));
}

beforeEach(() => {
  vi.clearAllMocks();
  listTemplates.mockResolvedValue([{ id: "t1", display_name: "Chrome" }]);
  deleteInstance.mockResolvedValue(undefined);
});

test("checkbox hidden without a profile volume", () => {
  open(mk({ profile_volume: null }));
  expect(screen.queryByLabelText(/persistent profile/i)).toBeNull();
});

test("ticking the profile checkbox sends deleteProfile=true", async () => {
  open(mk({ profile_volume: "profile-abc" }));
  const box = await screen.findByLabelText(/also delete my persistent profile for chrome/i);
  expect((box as HTMLInputElement).checked).toBe(false);
  fireEvent.click(box);
  fireEvent.change(screen.getByLabelText(/type/i), { target: { value: "Desk" } });
  fireEvent.click(screen.getAllByRole("button", { name: /^destroy$/i }).slice(-1)[0]!);
  await waitFor(() => expect(deleteInstance).toHaveBeenCalled());
  expect(deleteInstance.mock.calls[0]).toEqual(["i1", false, false, true]);
});
