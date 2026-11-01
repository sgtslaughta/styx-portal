import { MetricsOverview } from "@/components/system/metrics-overview";
import { UsersPanel } from "@/components/system/users-panel";
import { GroupsPanel } from "@/components/system/groups-panel";
import { SystemSettingsPanel } from "@/components/system/system-settings-panel";
import { StreamingPage } from "@/components/system/streaming-page";

// Composite panes; Tasks 10/11 replace these with the merged designs.
export const OverviewPane = () => <MetricsOverview />;
export const PeoplePane = () => (
  <div className="space-y-10"><UsersPanel /><GroupsPanel /></div>
);
export const SecurityPane = () => (
  <SystemSettingsPanel groups={["brute_force", "rate_limits", "password_policy", "quota"]} />
);
export const TimeoutsPane = () => (
  <SystemSettingsPanel groups={["sessions", "timeouts", "workstation_features"]} />
);
export const StreamingPane = () => <StreamingPage />;
