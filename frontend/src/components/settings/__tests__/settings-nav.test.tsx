import { render, screen, fireEvent } from "@testing-library/react";
import { useEffect } from "react";
import { describe, expect, test, vi } from "vitest";

vi.mock("../section-panels", () => ({
  OverviewPane: () => null, PeoplePane: () => null, SecurityPane: () => null,
  TimeoutsPane: () => null, StreamingPane: () => null,
}));
vi.mock("@/components/system/metrics-sessions", () => ({ MetricsSessions: () => null }));
vi.mock("@/components/system/metrics-logs", () => ({ MetricsLogs: () => null }));
vi.mock("@/components/system/health-panel", () => ({ HealthPanel: () => null }));
vi.mock("@/components/system/services-panel", () => ({ ServicesPanel: () => null }));
vi.mock("@/components/system/workstations-panel", () => ({ WorkstationsPanel: () => null }));
vi.mock("@/components/system/oauth-providers-panel", () => ({ OAuthProvidersPanel: () => null }));
vi.mock("@/components/system/image-manager", () => ({ ImageManager: () => null }));
vi.mock("@/components/system/connected-accounts", () => ({ ConnectedAccounts: () => null }));
vi.mock("../my-profiles", () => ({ MyProfiles: () => null }));
vi.mock("../matrix-card", () => ({ MatrixCard: () => null }));

import { SettingsNav } from "../settings-nav";
import { visibleCategories } from "../nav-config";
import { UnsavedProvider, useUnsaved } from "../unsaved-context";

function Seed({ n }: { n: number }) {
  const { setCount } = useUnsaved();
  useEffect(() => setCount(n), [n, setCount]);
  return null;
}

const setup = (n = 0, onSelect = vi.fn()) => {
  render(
    <UnsavedProvider>
      <Seed n={n} />
      <SettingsNav categories={visibleCategories(true)} activeId="overview" onSelect={onSelect} />
    </UnsavedProvider>,
  );
  return onSelect;
};

describe("SettingsNav", () => {
  test("find 'rate' leaves only Security and limits", () => {
    setup();
    fireEvent.change(screen.getByLabelText("Find a setting"), { target: { value: "rate" } });
    expect(screen.getByRole("button", { name: "Security and limits" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Overview" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Logs" })).toBeNull();
    expect(screen.getAllByRole("button")).toHaveLength(1);
  });

  test("active item has aria-current and gold-underline", () => {
    setup();
    const a = screen.getByRole("button", { name: "Overview" });
    expect(a).toHaveAttribute("aria-current", "page");
    expect(a).toHaveClass("gold-underline");
    expect(screen.getByRole("button", { name: "Health" })).not.toHaveAttribute("aria-current");
  });

  test("with unsaved changes, Cancel keeps the section; Discard switches", async () => {
    const onSelect = setup(3);
    fireEvent.click(screen.getByRole("button", { name: "Health" }));
    expect(await screen.findByText("Discard 3 unsaved changes?")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onSelect).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Health" }));
    fireEvent.click(await screen.findByRole("button", { name: "Discard" }));
    expect(onSelect).toHaveBeenCalledWith("health");
  });

  test("no prompt when nothing is unsaved", () => {
    const onSelect = setup(0);
    fireEvent.click(screen.getByRole("button", { name: "Health" }));
    expect(onSelect).toHaveBeenCalledWith("health");
  });
});
