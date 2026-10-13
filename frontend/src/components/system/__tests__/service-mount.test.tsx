import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";
import { api } from "@/api/client";
import { ServiceMount } from "../service-mount";
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
    log_excerpt: "boom", created_at: "", finished_at: "", steps: [{ id: "verify", label: "Check it answers", state: "failed", detail: "No answer" }] });
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
  expect(screen.queryByRole("alert")).toBeNull();
});
