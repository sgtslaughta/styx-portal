import { MetricsOverview } from "@/components/system/metrics-overview";
import { MetricsResources } from "@/components/system/metrics-resources";
import { UsersPanel } from "@/components/system/users-panel";
import { GroupsPanel } from "@/components/system/groups-panel";
import { SystemSettingsPanel } from "@/components/system/system-settings-panel";

// Composite panes; Tasks 10/11 replace these with the merged designs.
export const OverviewPane = () => (
  <div className="space-y-8"><MetricsOverview /><MetricsResources /></div>
);
export const PeoplePane = () => (
  <div className="space-y-8"><UsersPanel /><GroupsPanel /></div>
);
export const SecurityPane = () => (
  <SystemSettingsPanel groups={["brute_force", "rate_limits", "password_policy", "quota"]} />
);
export const TimeoutsPane = () => (
  <SystemSettingsPanel groups={["sessions", "timeouts", "workstation_features"]} />
);
export const StreamingPane = () => <SystemSettingsPanel groups={["webrtc"]} />;
