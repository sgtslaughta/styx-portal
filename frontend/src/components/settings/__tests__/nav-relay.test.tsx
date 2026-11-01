import { expect, test, vi } from "vitest";
vi.mock("../section-panels", () => ({ OverviewPane: () => null, PeoplePane: () => null, SecurityPane: () => null, TimeoutsPane: () => null, StreamingPane: () => null }));
vi.mock("@/components/system/relay-cost-page", () => ({ RelayCostPage: () => null }));
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
import { visibleCategories } from "../nav-config";

const labels = (cf: boolean) => visibleCategories(true, { cfAnalytics: cf }).flatMap((c) => c.sections.map((s) => s.label));

test("Relay cost only appears when cfAnalytics is on", () => {
  expect(labels(false)).not.toContain("Relay cost");
  expect(labels(true)).toContain("Relay cost");
});
