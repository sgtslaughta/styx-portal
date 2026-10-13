import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { AccessSection } from "../service-form-access";
const preset = { id: "jellyfin", name: "Jellyfin", icon: null, default_port: 8096, mount_mode: "path", auth_mode: "sso",
  bypass_rules: [{ path_prefix: "/jellyfin/", required_header: "X-Emby-Token" }], health_path: null, verify_tls: true,
  base_url_hint: null, warnings: [], subpath: { methods: [{}] } } as never;
function Harness(p: { f?: object }) {
  const [f, setF] = useState({ slug: "jellyfin", mount_mode: "path", auth_mode: "sso", bypass_rules: [],
    allowed_groups: [], pass_identity: false, frame_ok: true, ...p.f } as never);
  return <><AccessSection f={f} set={(k, v) => setF((o: object) => ({ ...o, [k]: v }) as never)} preset={preset} groups={[]} errors={{}} />
    <output data-testid="state">{JSON.stringify(f)}</output></>;
}
const state = () => JSON.parse(screen.getByTestId("state").textContent!);
it("shows the managed mount line", () => {
  render(<Harness />);
  expect(screen.getByText("Path /jellyfin, configured by Styx")).toBeInTheDocument();
});
it("native apps toggles bypass mode and shows the risk", () => {
  render(<Harness />);
  fireEvent.click(screen.getByRole("switch", { name: /allow native apps/i }));
  expect(state().auth_mode).toBe("sso-with-bypass");
  expect(state().bypass_rules).toHaveLength(1);
  expect(screen.getByRole("alert")).toHaveTextContent(/exposed to the internet/i);
  fireEvent.click(screen.getByRole("switch", { name: /allow native apps/i }));
  expect(state().auth_mode).toBe("sso");
});
it("open without overlay flips frame_ok", () => {
  render(<Harness />);
  fireEvent.click(screen.getByText("Advanced"));
  fireEvent.click(screen.getByRole("switch", { name: /open without overlay/i }));
  expect(state().frame_ok).toBe(false);
});
it("focus mode line", () => {
  render(<Harness f={{ mount_mode: "cookie-root" }} />);
  expect(screen.getByText("Focus: opens full screen")).toBeInTheDocument();
});
