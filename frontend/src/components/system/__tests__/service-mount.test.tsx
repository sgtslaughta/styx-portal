import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, beforeEach } from "vitest";
import { toast } from "sonner";
import { ServiceMount as SM, pollWhile } from "../service-mount";
import { api } from "@/api/client";
const ServiceMount = SM;
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
beforeEach(() => vi.clearAllMocks());
vi.mock("@/api/client", async (o) => ({ ...(await o<object>()), api: {
  mountPlan: vi.fn(), mountApply: vi.fn(), mountLatest: vi.fn(), updateService: vi.fn() } }));
const svc = { id: "s1", slug: "sonarr", name: "Sonarr", kind: "docker-local", mount_mode: "path" } as never;
const wrap = (ui: React.ReactNode) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);
const CH = [{ target: "/config/config.xml", key: "/Config/UrlBase", old: "", new: "/sonarr" }];
const notFound = Object.assign(new Error("nf"), { status: 404 });

it("adopted container asks for consent with the change table", async () => {
  vi.mocked(api.mountPlan).mockResolvedValue({ method: "config_file", changes: CH, needs_consent: true, reason: null });
  vi.mocked(api.mountLatest).mockRejectedValue(notFound);
  vi.mocked(api.mountApply).mockResolvedValue({ job_id: "j" });
  wrap(<ServiceMount service={svc} />);
  fireEvent.click(await screen.findByRole("button", { name: "Set base path to /sonarr" }));
  expect(await screen.findByRole("dialog", { name: "Change Sonarr's settings?" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "/sonarr" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Restart Sonarr and apply" }));
  await waitFor(() => expect(api.mountApply).toHaveBeenCalledWith("s1", true));
});

it("rollback shows reason, log and both recoveries", async () => {
  vi.mocked(api.mountPlan).mockResolvedValue({ method: "config_file", changes: CH, needs_consent: false, reason: null });
  vi.mocked(api.mountLatest).mockResolvedValue({ id: "j", state: "rolled_back", changes: CH, backup_dir: "/b",
    log_excerpt: "boom", created_at: "", finished_at: "", steps: [{ id: "verify", label: "Check the app responds", state: "failed", detail: "No answer" }] });
  wrap(<ServiceMount service={svc} />);
  expect(await screen.findByText(/Styx put its settings back/)).toBeInTheDocument();
  expect(screen.getByText("boom")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Use focus mode instead" })).toBeInTheDocument();
});

it("no job yet (404) shows the plan, not an error", async () => {
  vi.mocked(api.mountPlan).mockResolvedValue({ method: null, changes: [], needs_consent: true, reason: "Styx can't find Sonarr's settings file in the container." });
  vi.mocked(api.mountLatest).mockRejectedValue(notFound);
  wrap(<ServiceMount service={svc} />);
  expect(await screen.findByText(/can't find Sonarr's settings file/)).toBeInTheDocument();
  expect(screen.queryByText(/Couldn.t (check|switch)/)).toBeNull();
});

const rolled = { id: "j", state: "rolled_back", changes: CH, backup_dir: "/b", log_excerpt: "boom", created_at: "", finished_at: "", steps: [] } as never;

it("focus mode switch updates the service and notifies", async () => {
  vi.mocked(api.mountPlan).mockResolvedValue({ method: "config_file", changes: CH, needs_consent: false, reason: null });
  vi.mocked(api.mountLatest).mockResolvedValue(rolled);
  const updated = { ...(svc as object), mount_mode: "cookie-root" };
  vi.mocked(api.updateService).mockResolvedValue(updated as never);
  const onChanged = vi.fn();
  wrap(<ServiceMount service={svc} onChanged={onChanged} />);
  fireEvent.click(await screen.findByRole("button", { name: "Use focus mode instead" }));
  await waitFor(() => expect(onChanged).toHaveBeenCalledWith(updated));
  expect(vi.mocked(api.updateService).mock.calls[0]![1]).toMatchObject({ mount_mode: "cookie-root" });
  expect(toast.success).toHaveBeenCalledWith("Sonarr now opens in focus mode.");
});

it("done job with pending changes still offers the Set button", async () => {
  vi.mocked(api.mountPlan).mockResolvedValue({ method: "config_file", changes: CH, needs_consent: false, reason: null });
  vi.mocked(api.mountLatest).mockResolvedValue({ ...(rolled as object), state: "done" } as never);
  wrap(<ServiceMount service={svc} />);
  expect(await screen.findByRole("button", { name: "Set base path to /sonarr" })).toBeInTheDocument();
});

it("polls only while pending or running", () => {
  expect(pollWhile("running")).toBe(1000);
  expect(pollWhile("pending")).toBe(1000);
  for (const st of ["done", "rolled_back", "failed", undefined]) expect(pollWhile(st)).toBe(false);
});

it("failed job shows the backup path", async () => {
  vi.mocked(api.mountPlan).mockResolvedValue({ method: "config_file", changes: CH, needs_consent: false, reason: null });
  vi.mocked(api.mountLatest).mockResolvedValue({ ...(rolled as object), state: "failed" } as never);
  wrap(<ServiceMount service={svc} />);
  expect(await screen.findByText(/Your backup is in \/b/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
});

it("409 on apply toasts the backend detail", async () => {
  vi.mocked(api.mountPlan).mockResolvedValue({ method: "config_file", changes: CH, needs_consent: false, reason: null });
  vi.mocked(api.mountLatest).mockRejectedValue(notFound);
  vi.mocked(api.mountApply).mockRejectedValue(new Error("A change is already running for this service"));
  wrap(<ServiceMount service={svc} />);
  fireEvent.click(await screen.findByRole("button", { name: "Set base path to /sonarr" }));
  await waitFor(() => expect(toast.error).toHaveBeenCalledWith("A change is already running for this service"));
});

it("consent Cancel closes without applying", async () => {
  vi.mocked(api.mountPlan).mockResolvedValue({ method: "config_file", changes: CH, needs_consent: true, reason: null });
  vi.mocked(api.mountLatest).mockRejectedValue(notFound);
  wrap(<ServiceMount service={svc} />);
  fireEvent.click(await screen.findByRole("button", { name: "Set base path to /sonarr" }));
  fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(api.mountApply).not.toHaveBeenCalled();
});

it("job going straight to done after apply refetches the plan and drops the Set button", async () => {
  vi.mocked(api.mountPlan).mockResolvedValueOnce({ method: "config_file", changes: CH, needs_consent: false, reason: null })
    .mockResolvedValue({ method: "config_file", changes: [], needs_consent: false, reason: null });
  vi.mocked(api.mountLatest).mockRejectedValueOnce(notFound)
    .mockResolvedValue({ ...(rolled as object), state: "done" } as never);
  vi.mocked(api.mountApply).mockResolvedValue({ job_id: "j" });
  wrap(<ServiceMount service={svc} />);
  fireEvent.click(await screen.findByRole("button", { name: "Set base path to /sonarr" }));
  expect(await screen.findByText(/Base path set\. Sonarr answers at \/sonarr/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Set base path to /sonarr" })).toBeNull();
});

it("consent dialog has a stacked list for small widths", async () => {
  vi.mocked(api.mountPlan).mockResolvedValue({ method: "config_file", changes: CH, needs_consent: true, reason: null });
  vi.mocked(api.mountLatest).mockRejectedValue(notFound);
  wrap(<ServiceMount service={svc} />);
  fireEvent.click(await screen.findByRole("button", { name: "Set base path to /sonarr" }));
  const dlg = await screen.findByRole("dialog");
  const list = dlg.querySelector("dl");
  expect(list).not.toBeNull();
  expect(list).toHaveClass("sm:hidden");
  expect(list).toHaveTextContent("(not set)");
  expect(dlg.querySelector("table")).toHaveClass("hidden", "sm:table");
});
