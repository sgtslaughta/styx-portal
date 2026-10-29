import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
const choose = vi.fn((_g: string, _n: string, run: (m: string) => void) => run("same_tab"));
vi.mock("@/components/open-prompt", () => ({ useOpenChoice: () => choose }));
const openPending = vi.fn(async (_m: string, _l: string, get: () => Promise<string>) => { await get(); });
vi.mock("@/lib/connect-wipe", () => ({ openPending: (...a: Parameters<typeof openPending>) => openPending(...a) }));
import { ActionBar } from "../action-bar";
import type { Instance } from "@/lib/types";

test("instance Connect uses the Workspaces preference", async () => {
  const inst = { id: "i1", name: "Desk", subdomain: "desk", status: "running" } as Instance;
  render(<QueryClientProvider client={new QueryClient()}><ActionBar instance={inst} /></QueryClientProvider>);
  fireEvent.click(screen.getByRole("button", { name: /connect/i }));
  expect(choose).toHaveBeenCalledWith("workspaces", "Desk", expect.any(Function));
  expect(openPending.mock.calls[0]!.slice(0, 2)).toEqual(["same_tab", "Launching Desk…"]);
  await expect(openPending.mock.calls[0]![2]()).resolves.toBe("/desktop/desk");
});
