import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

const me = vi.fn();
const setOpenPrefs = vi.fn();
vi.mock("@/api/client", () => ({ api: { me: () => me(), setOpenPrefs: (p: unknown) => setOpenPrefs(p) } }));
const toastError = vi.fn();
vi.mock("sonner", () => ({ toast: { error: (m: string) => toastError(m) } }));
import { OpenPrefProvider, useOpenChoice } from "../open-prompt";

const base = { id: "u", username: "a", email: null, role: "user", open_workspaces: null, open_apps: null };
const run = vi.fn();
function Btn() {
  const choose = useOpenChoice();
  return <button onClick={() => choose("apps", "Sonarr", run)}>go</button>;
}
function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><OpenPrefProvider><Btn /></OpenPrefProvider></QueryClientProvider>);
  return qc;
}
beforeEach(() => { run.mockReset(); setOpenPrefs.mockReset(); toastError.mockReset(); me.mockResolvedValue(base); });

test("set preference runs directly, no dialog", async () => {
  me.mockResolvedValue({ ...base, open_apps: "same_tab" });
  setup();
  await waitFor(() => expect(me).toHaveBeenCalled());
  await new Promise((r) => setTimeout(r));
  fireEvent.click(screen.getByText("go"));
  expect(run).toHaveBeenCalledWith("same_tab");
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("unset prompts; new tab runs first, then saves", async () => {
  setOpenPrefs.mockResolvedValue({ ...base, open_apps: "new_tab" });
  setup();
  fireEvent.click(screen.getByText("go"));
  expect(await screen.findByRole("dialog", { name: "Open Sonarr" })).toBeInTheDocument();
  expect(screen.getByRole("checkbox", { name: "Remember for all apps" })).toBeChecked();
  await waitFor(() => expect(screen.getByRole("button", { name: "Open in new tab" })).toHaveFocus());
  fireEvent.click(screen.getByRole("button", { name: "Open in new tab" }));
  expect(run).toHaveBeenCalledWith("new_tab");
  await waitFor(() => expect(setOpenPrefs).toHaveBeenCalledWith({ open_apps: "new_tab" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

test("same tab saves BEFORE running (navigation would abort the PUT)", async () => {
  const order: string[] = [];
  setOpenPrefs.mockImplementation(async () => { order.push("save"); return base; });
  run.mockImplementation(() => order.push("run"));
  setup();
  fireEvent.click(screen.getByText("go"));
  fireEvent.click(await screen.findByRole("button", { name: "Open here" }));
  await waitFor(() => expect(order).toEqual(["save", "run"]));
});

test("remember off: opens, saves nothing", async () => {
  setup();
  fireEvent.click(screen.getByText("go"));
  fireEvent.click(await screen.findByRole("checkbox", { name: "Remember for all apps" }));
  fireEvent.click(screen.getByRole("button", { name: "Open in new tab" }));
  expect(run).toHaveBeenCalledWith("new_tab");
  expect(setOpenPrefs).not.toHaveBeenCalled();
});

test("escape cancels: nothing opens or saves", async () => {
  setup();
  fireEvent.click(screen.getByText("go"));
  fireEvent.keyDown(await screen.findByRole("dialog"), { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(run).not.toHaveBeenCalled();
  expect(setOpenPrefs).not.toHaveBeenCalled();
});

test("save failure toasts; the open still happened", async () => {
  setOpenPrefs.mockRejectedValue(new Error("x"));
  setup();
  fireEvent.click(screen.getByText("go"));
  fireEvent.click(await screen.findByRole("button", { name: "Open in new tab" }));
  expect(run).toHaveBeenCalled();
  await waitFor(() => expect(toastError).toHaveBeenCalledWith("Couldn't save your choice"));
});

test("without a provider: runs new_tab", () => {
  render(<Btn />);
  fireEvent.click(screen.getByText("go"));
  expect(run).toHaveBeenCalledWith("new_tab");
});
