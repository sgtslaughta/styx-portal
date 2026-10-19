import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

vi.mock("@/hooks/use-auth", () => ({ useAuth: () => ({ user: { role: "user" }, loading: false }) }));
vi.mock("@/hooks/use-templates", () => ({ useTemplates: () => ({ data: [] }) }));
vi.mock("@/components/layout/header", () => ({ Header: () => null }));
vi.mock("@/components/instances/instance-workspace", () => ({ InstanceWorkspace: () => <p>ws</p> }));
vi.mock("@/components/home/apps-grid", () => ({ AppsGrid: () => <p>apps-grid</p> }));
vi.mock("@/components/templates/template-grid", () => ({ TemplateGrid: () => null }));
vi.mock("@/components/templates/registry-browser", () => ({ RegistryBrowser: () => null }));
vi.mock("@/components/templates/launch-modal", () => ({ LaunchModal: () => null }));
vi.mock("@/components/settings/settings-layout", () => ({ SettingsLayout: () => null }));

import App from "../App";

// jsdom has no layout: assert the scroll-container classes that keep the document from overflowing.
test("Workspaces wrapper constrains its height", () => {
  render(<App />);
  expect(screen.getByText("ws").parentElement!.className).toContain("min-h-0");
});

test("Apps wrapper is its own scroll container", () => {
  localStorage.setItem("styx.home.tab", "apps");
  render(<App />);
  const cls = screen.getByText("apps-grid").parentElement!.className;
  expect(cls).toContain("overflow-y-auto");
  expect(cls).toContain("min-h-0");
});
