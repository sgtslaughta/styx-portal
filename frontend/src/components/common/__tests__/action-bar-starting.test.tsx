import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
vi.mock("@/components/open-prompt", () => ({ useOpenChoice: () => vi.fn() }));
import { ActionBar } from "../action-bar";
import type { Instance } from "@/lib/types";

test("starting instance has a disabled button and no Connect", () => {
  const inst = { id: "i1", name: "Desk", subdomain: "desk", status: "starting" } as Instance;
  render(<QueryClientProvider client={new QueryClient()}><ActionBar instance={inst} /></QueryClientProvider>);
  expect(screen.queryByRole("button", { name: /connect/i })).toBeNull();
  expect(screen.getByTitle("Starting…")).toBeDisabled();
});
