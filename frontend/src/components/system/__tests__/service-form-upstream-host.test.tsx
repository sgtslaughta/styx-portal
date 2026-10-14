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
  if (!initial) { change("Slug", "g"); change("Name", "G"); change("Upstream URL", "https://10.0.0.1"); }
  return onSubmit;
}

const existing: ProxiedService = {
  id: "s1", slug: "jf", name: "Jellyfin", icon_kind: "auto", icon_etag: "e", kind: "url", upstream_url: "http://10.0.0.2:8096",
  container: null, container_port: null, upstream_fallback: null, mount_mode: "path", auth_mode: "sso",
  bypass_rules: [], allowed_groups: [], verify_tls: true, upstream_host: "app.proxy.test", health_path: null,
  health_status: "healthy", health_checked_at: null, preset_id: null, enabled: true, created_at: "", updated_at: "",
  mount_managed: false, needs_setup: false, pass_identity: false, frame_ok: true,
};

describe("ServiceForm upstream reverse proxy", () => {
  test("switch reveals the hostname field and the warning", () => {
    setup();
    expect(screen.queryByLabelText("Site hostname")).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(SW));
    expect(screen.getByLabelText("Site hostname")).toBeInTheDocument();
    expect(screen.getByText("Links may leave Styx")).toBeInTheDocument();
  });

  test("warning names the hostname", () => {
    setup();
    fireEvent.click(screen.getByLabelText(SW));
    change("Site hostname", "unraid.home.lan");
    expect(screen.getByText(/The app will think its address is unraid\.home\.lan\./)).toBeInTheDocument();
  });

  test("invalid hostname shows the message and blocks save", () => {
    setup();
    fireEvent.click(screen.getByLabelText(SW));
    change("Site hostname", "http://x");
    expect(screen.getByText("Enter a hostname like unraid.home.lan — no http://, port or path.")).toBeInTheDocument();
    expect(save()).toBeDisabled();
    change("Site hostname", "");
    expect(save()).toBeDisabled();      // on but empty
  });

  test("submits the lowercased hostname", () => {
    const onSubmit = setup();
    fireEvent.click(screen.getByLabelText(SW));
    change("Site hostname", "Unraid.Home.LAN");
    fireEvent.click(save());
    expect(onSubmit.mock.calls[0]?.[0]).toMatchObject({ upstream_host: "unraid.home.lan" });
  });

  test("submits null when the switch is toggled off again", () => {
    const onSubmit = setup();
    fireEvent.click(screen.getByLabelText(SW));
    change("Site hostname", "x.lan");
    fireEvent.click(screen.getByLabelText(SW));
    fireEvent.click(save());
    expect(onSubmit.mock.calls[0]?.[0]).toMatchObject({ upstream_host: null });
  });

  test("existing service with a host opens with the switch on", () => {
    setup(existing);
    expect(screen.getByLabelText(SW)).toBeChecked();
    expect(screen.getByLabelText("Site hostname")).toHaveValue("app.proxy.test");
  });

  test("not offered for docker-local", () => {
    setup();
    change("Kind", "docker-local");
    expect(screen.queryByLabelText(SW)).not.toBeInTheDocument();
  });
});
