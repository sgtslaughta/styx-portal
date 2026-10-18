import { render, screen, fireEvent } from "@testing-library/react";
import { describe, test, expect, vi } from "vitest";
import { ServiceForm } from "../service-form";
import type { ProxiedService } from "@/api/client";

const ACK = /I understand that this app runs on the same origin as Styx/;
const SW = "Upstream is a reverse proxy";
const change = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
const save = () => screen.getByRole("button", { name: /^save$/i });

function setup(initial?: ProxiedService) {
  const onSubmit = vi.fn();
  render(<ServiceForm presets={[]} groups={[]} initial={initial} onSubmit={onSubmit} onCancel={() => {}} />);
  fireEvent.click(screen.getByLabelText(ACK));
  if (!initial) { change("Slug", "g"); change("Name", "G"); change("Upstream URL", "https://unraid.home.lan"); }
  return onSubmit;
}

const existing: ProxiedService = {
  id: "s1", slug: "jf", name: "Jellyfin", icon_kind: "auto", icon_etag: "e", kind: "url", upstream_url: "http://jf.lan:8096",
  container: null, container_port: null, upstream_fallback: null, mount_mode: "path", auth_mode: "sso",
  bypass_rules: [], allowed_groups: [], verify_tls: true, upstream_is_proxy: true, health_path: null,
  health_status: "healthy", health_checked_at: null, preset_id: null, enabled: true, created_at: "", updated_at: "",
  mount_managed: false, needs_setup: false, pass_identity: false, frame_ok: true,
};

const IP_ERROR = "A reverse proxy picks the site by hostname, so the upstream address must use one (e.g. https://unraid.home.lan).";

describe("ServiceForm upstream reverse proxy", () => {
  test("switch reveals the warning; there is no hostname field", () => {
    setup();                                   // hostname upstream: on by default
    fireEvent.click(screen.getByLabelText(SW));
    expect(screen.queryByText("Links may leave Styx")).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(SW));
    expect(screen.queryByLabelText("Site hostname")).not.toBeInTheDocument();
    expect(screen.getByText("Links may leave Styx")).toBeInTheDocument();
    expect(screen.getByText(/Styx sends that hostname to it\./)).toBeInTheDocument();
  });

  test("warning text is static and links to the proxy docs", () => {
    setup();
    expect(screen.getByText(/Redirects are kept inside Styx, but links the app writes into its pages with its own hostname still leave Styx\./)).toBeInTheDocument();
    const alert = screen.getByText("Links may leave Styx").closest("[role=alert]") as HTMLElement;
    expect(alert.querySelector("a")).toHaveAttribute("href", "/docs/SERVICES/#apps-behind-a-reverse-proxy");
  });

  test.each(["https://10.0.0.1", "http://192.168.1.96:8080/x", "https://[::1]:8443"])("IP literal %s blocks save when on", (url) => {
    setup();
    change("Upstream URL", url);
    fireEvent.click(screen.getByLabelText(SW));
    expect(screen.getByText(IP_ERROR)).toBeInTheDocument();
    expect(save()).toBeDisabled();
    fireEvent.click(screen.getByLabelText(SW));
    expect(screen.queryByText(IP_ERROR)).not.toBeInTheDocument();
    expect(save()).toBeEnabled();
  });

  test("submits upstream_is_proxy true when on", () => {
    const onSubmit = setup();
    fireEvent.click(save());
    expect(onSubmit.mock.calls[0]?.[0]).toMatchObject({ upstream_is_proxy: true });
  });

  test("submits upstream_is_proxy false when toggled off", () => {
    const onSubmit = setup();
    fireEvent.click(screen.getByLabelText(SW));
    fireEvent.click(save());
    expect(onSubmit.mock.calls[0]?.[0]).toMatchObject({ upstream_is_proxy: false });
  });

  test("existing proxy service opens with the switch on", () => {
    setup(existing);
    expect(screen.getByLabelText(SW)).toBeChecked();
  });

  test("not offered for docker-local, and cleared when switching kind", () => {
    const onSubmit = setup();
    fireEvent.click(screen.getByLabelText(SW));
    change("Kind", "docker-local");
    expect(screen.queryByLabelText(SW)).not.toBeInTheDocument();
    change("Container", "c");
    change("Container port", "80");
    fireEvent.click(save());
    expect(onSubmit.mock.calls[0]?.[0]).toMatchObject({ upstream_is_proxy: false });
  });
});

describe("ServiceForm upstream reverse proxy default", () => {
  const sw = () => screen.getByRole("switch", { name: SW });
  test("a hostname upstream turns the switch on; an IP turns it off", () => {
    setup();
    expect(sw()).toBeChecked();
    change("Upstream URL", "https://192.168.1.96:8443");
    expect(sw()).not.toBeChecked();
    change("Upstream URL", "http://localhost:8080");
    expect(sw()).not.toBeChecked();
  });
  test("a manual choice sticks while the address is edited", () => {
    setup();
    fireEvent.click(sw());
    change("Upstream URL", "https://nas.home.lan");
    expect(sw()).not.toBeChecked();
  });
  test("editing an existing service keeps its saved choice until the address changes", () => {
    setup({ ...existing, upstream_is_proxy: false });
    expect(sw()).not.toBeChecked();
  });
});
