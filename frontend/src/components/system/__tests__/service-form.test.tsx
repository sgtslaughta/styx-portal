import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, test, expect, vi } from "vitest";
import { ServiceForm } from "../service-form";
import { RISK } from "@/components/common/risk-callout";
import type { ProxiedService } from "@/api/client";

const presets = [{ id: "sonarr", name: "Sonarr", icon: null, default_port: 8989, mount_mode: "path" as const,
  auth_mode: "sso-with-bypass" as const, bypass_rules: [{ path_prefix: "/sonarr/api", required_header: "X-Api-Key" }],
  health_path: "/sonarr/ping", verify_tls: true, base_url_hint: "URL Base = /sonarr", warnings: [] }];

type Props = Parameters<typeof ServiceForm>[0];
function setup(extra: Partial<Props> = {}) {
  const onSubmit = vi.fn();
  render(<ServiceForm presets={presets} groups={[]} onSubmit={onSubmit} onCancel={() => {}} {...extra} />);
  return onSubmit;
}
const change = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
const save = () => screen.getByRole("button", { name: /^save$/i });

function fillUrl() {
  change("Slug", "x"); change("Name", "X"); change("Upstream URL", "http://10.0.0.1:80");
}

const existing: ProxiedService = {
  id: "s1", slug: "jf", name: "Jellyfin", icon: null, kind: "url", upstream_url: "http://10.0.0.2:8096",
  container: null, container_port: null, upstream_fallback: null, mount_mode: "path", auth_mode: "sso",
  bypass_rules: [], allowed_groups: [], verify_tls: true, health_path: null, health_status: "healthy",
  health_checked_at: null, preset_id: null, enabled: true, created_at: "", updated_at: "",
};

describe("ServiceForm risk callouts", () => {
  test("bypass rule callout appears and empty prefix blocks save", () => {
    setup();
    change("Auth mode", "sso-with-bypass");
    fireEvent.click(screen.getByRole("button", { name: /add bypass rule/i }));
    expect(screen.getByText(RISK.bypass("<prefix>"))).toBeInTheDocument();
    expect(save()).toBeDisabled();
  });

  test("bypass callout shows the typed prefix; a valid prefix enables save", () => {
    setup();
    fillUrl();
    change("Auth mode", "sso-with-bypass");
    fireEvent.click(screen.getByRole("button", { name: /add bypass rule/i }));
    fireEvent.change(screen.getByLabelText("Bypass path prefix"), { target: { value: "/x/api" } });
    expect(screen.getByText(RISK.bypass("/x/api"))).toBeInTheDocument();
    expect(save()).toBeEnabled();
    fireEvent.change(screen.getByLabelText("Bypass path prefix"), { target: { value: "x/api" } });
    expect(save()).toBeDisabled();
    expect(screen.getByText(/must start with \//i)).toBeInTheDocument();
  });

  test("app-native and tls callouts", () => {
    setup();
    expect(screen.queryByText(RISK.appNative)).not.toBeInTheDocument();
    expect(screen.queryByText(RISK.tls)).not.toBeInTheDocument();
    change("Auth mode", "app-native");
    expect(screen.getByText(RISK.appNative)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Verify upstream TLS"));
    expect(screen.getByText(RISK.tls)).toBeInTheDocument();
  });

  test("cookie-root callout", () => {
    setup();
    change("Mount mode", "cookie-root");
    expect(screen.getByText(RISK.cookieRoot)).toBeInTheDocument();
  });

  test("callout texts match spec section 9 verbatim", () => {
    expect(RISK.bypass("<prefix>")).toBe(
      "Requests matching <prefix> are reachable from the internet WITHOUT Styx login. Only the app's own credential and rate limiting protect them.");
    expect(RISK.appNative).toBe("Styx does not authenticate this service. The app must enforce its own login.");
    expect(RISK.tls).toBe("Upstream certificate is not verified. Traffic between Styx and this host can be intercepted on your LAN.");
    expect(RISK.cookieRoot).toContain("Takes over the root of the hostname for this browser. One service at a time. Mobile apps cannot use this mode.");
  });

  test("bypass rules are dropped on submit when auth mode is no longer sso-with-bypass", () => {
    const onSubmit = setup();
    fillUrl();
    change("Auth mode", "sso-with-bypass");
    fireEvent.click(screen.getByRole("button", { name: /add bypass rule/i }));
    fireEvent.change(screen.getByLabelText("Bypass path prefix"), { target: { value: "/a" } });
    change("Auth mode", "sso");
    fireEvent.click(save());
    expect(onSubmit.mock.calls[0]?.[0]).toMatchObject({ auth_mode: "sso", bypass_rules: [] });
  });
});

describe("ServiceForm behaviour", () => {
  test("switching kind to docker-local clears upstream_url", () => {
    const onSubmit = setup();
    fillUrl();
    change("Kind", "docker-local");
    change("Container", "c");
    change("Container port", "80");
    fireEvent.click(save());
    expect(onSubmit.mock.calls[0]?.[0]).toMatchObject({ kind: "docker-local", upstream_url: null, container: "c", container_port: 80 });
  });

  test("switching kind back to url clears container fields", () => {
    const onSubmit = setup();
    change("Kind", "docker-local");
    change("Container", "c");
    change("Container port", "80");
    change("Kind", "url");
    fillUrl();
    fireEvent.click(save());
    expect(onSubmit.mock.calls[0]?.[0]).toMatchObject({ kind: "url", container: null, container_port: null });
  });

  test("preset fills fields and shows hint", () => {
    setup();
    change("Preset", "sonarr");
    expect(screen.getByLabelText("Slug")).toHaveValue("sonarr");
    expect(screen.getByLabelText("Name")).toHaveValue("Sonarr");
    expect(screen.getByLabelText("Bypass path prefix")).toHaveValue("/sonarr/api");
    expect(screen.getByText(/URL Base = \/sonarr/)).toBeInTheDocument();
  });

  test("save disabled until valid; slug and url rules mirror the backend", () => {
    setup();
    expect(save()).toBeDisabled();
    change("Name", "X"); change("Upstream URL", "http://u:1");
    change("Slug", "api");
    expect(screen.getByText(/reserved/i)).toBeInTheDocument();
    expect(save()).toBeDisabled();
    change("Slug", "Bad_Slug");
    expect(screen.getByText(/lowercase letters, digits and hyphens/i)).toBeInTheDocument();
    change("Slug", "ok-1");
    expect(save()).toBeEnabled();
    change("Upstream URL", "http://user:pw@host");
    expect(screen.getByText(/no credentials/i)).toBeInTheDocument();
    expect(save()).toBeDisabled();
    change("Upstream URL", "ftp://host");
    expect(save()).toBeDisabled();
    change("Upstream URL", "https://host:8443/base");
    expect(save()).toBeEnabled();
  });

  test("container name, port range and health path validated", () => {
    setup();
    fillUrl();
    change("Health path", "ping");
    expect(save()).toBeDisabled();
    change("Health path", "/ping");
    change("Kind", "docker-local");
    change("Container", "-bad name");
    change("Container port", "70000");
    expect(save()).toBeDisabled();
    expect(screen.getByText(/1 and 65535/)).toBeInTheDocument();
    change("Container", "good_name");
    change("Container port", "8080");
    expect(save()).toBeEnabled();
  });

  test("edit mode locks the slug", () => {
    setup({ initial: existing });
    expect(screen.getByLabelText("Slug")).toBeDisabled();
    expect(save()).toBeEnabled();
  });

  test("docker discovery dropdown lists containers with ports and prefills", async () => {
    const loadContainers = vi.fn().mockResolvedValue([
      { name: "jellyfin", image: "jf", ports: [8096, 8920], networks: [], suggested_preset: null },
      { name: "db", image: "pg", ports: [], networks: [], suggested_preset: null },
    ]);
    const onSubmit = setup({ loadContainers });
    change("Kind", "docker-local");
    await waitFor(() => expect(screen.getByRole("option", { name: /jellyfin.*8096/ })).toBeInTheDocument());
    const sel = screen.getByLabelText("Container");
    fireEvent.change(sel, { target: { value: "jellyfin" } });
    expect(screen.getByLabelText("Container port")).toHaveValue(8096);
    fireEvent.click(screen.getByRole("button", { name: "8920" }));
    expect(screen.getByLabelText("Container port")).toHaveValue(8920);
    change("Slug", "jf"); change("Name", "JF");
    fireEvent.click(save());
    expect(onSubmit.mock.calls[0]?.[0]).toMatchObject({ container: "jellyfin", container_port: 8920 });
  });

  test("discovery failure falls back to manual entry with a message", async () => {
    setup({ loadContainers: vi.fn().mockRejectedValue(new Error("no docker")) });
    change("Kind", "docker-local");
    expect(await screen.findByText(/no docker/)).toBeInTheDocument();
    expect(screen.getByLabelText("Container")).toBeInTheDocument();
  });
});

describe("ServiceForm saving and server errors", () => {
  test("save is disabled while saving and 422 field errors show next to the field", async () => {
    let resolve!: (v: Record<string, string>) => void;
    const onSubmit = vi.fn(() => new Promise<Record<string, string>>((r) => { resolve = r; }));
    setup({ onSubmit });
    fillUrl();
    fireEvent.click(save());
    await waitFor(() => expect(save()).toBeDisabled());
    expect(onSubmit).toHaveBeenCalledTimes(1);
    resolve({ slug: "Slug already in use" });
    expect(await screen.findByText("Slug already in use")).toBeInTheDocument();
    await waitFor(() => expect(save()).toBeEnabled());
    change("Slug", "y");
    expect(screen.queryByText("Slug already in use")).not.toBeInTheDocument();
  });
});
