import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";

const m = vi.hoisted(() => ({ stopInstance: vi.fn(), toastError: vi.fn(), retry: vi.fn() }));
vi.mock("@/api/client", () => ({ api: { stopInstance: m.stopInstance }, ApiError: class extends Error {} }));
vi.mock("sonner", () => ({ toast: { error: m.toastError, success: vi.fn() } }));
import { ActiveNow, NeedsLook } from "../overview-lists";

const row = { id: "i1", text: "Chromium", tone: "ok" as const, instanceId: "1", kind: "Container" };
const wrap = (ui: React.ReactElement) => render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);
beforeEach(() => vi.clearAllMocks());

test("End asks for confirmation before stopping", async () => {
  m.stopInstance.mockResolvedValue({});
  wrap(<ActiveNow rows={[row]} ready retry={m.retry} />);
  fireEvent.click(screen.getByRole("button", { name: "End" }));
  expect(m.stopInstance).not.toHaveBeenCalled();
  fireEvent.click((await screen.findAllByRole("button", { name: "End" })).slice(-1)[0]!);
  await waitFor(() => expect(m.stopInstance).toHaveBeenCalledWith("1"));
});

test("a failed End shows an error toast", async () => {
  m.stopInstance.mockRejectedValue(new Error("boom"));
  wrap(<ActiveNow rows={[row]} ready retry={m.retry} />);
  fireEvent.click(screen.getByRole("button", { name: "End" }));
  fireEvent.click((await screen.findAllByRole("button", { name: "End" })).slice(-1)[0]!);
  await waitFor(() => expect(m.toastError).toHaveBeenCalledWith(expect.stringContaining("boom")));
});

test("a failed query shows Couldn't load with a working Retry", () => {
  wrap(<NeedsLook rows={[]} ready={false} error retry={m.retry} />);
  expect(screen.queryByText("Loading…")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(m.retry).toHaveBeenCalled();
});
