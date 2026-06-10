import type { ComponentType } from "react";
import {
  Activity, Terminal, Cpu, ScrollText, Users, KeyRound, HardDrive,
  Link2, BarChart3, Shield, UserCircle, Heart, MonitorSmartphone,
} from "lucide-react";
import { MetricsOverview } from "@/components/system/metrics-overview";
import { MetricsSessions } from "@/components/system/metrics-sessions";
import { MetricsResources } from "@/components/system/metrics-resources";
import { MetricsLogs } from "@/components/system/metrics-logs";
import { HealthPanel } from "@/components/system/health-panel";
import { UsersPanel } from "@/components/system/users-panel";
import { WorkstationsPanel } from "@/components/system/workstations-panel";
import { OAuthProvidersPanel } from "@/components/system/oauth-providers-panel";
import { ImageManager } from "@/components/system/image-manager";
import { ConnectedAccounts } from "@/components/system/connected-accounts";

export type SettingsSection = {
  id: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  description: string;
  tooltip: string;
  Component: ComponentType;
};

export type SettingsCategory = {
  id: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  adminOnly: boolean;
  sections: SettingsSection[];
};

export const CATEGORIES: SettingsCategory[] = [
  {
    id: "monitoring", label: "Monitoring", icon: BarChart3, adminOnly: true,
    sections: [
      { id: "overview", label: "Overview", icon: Activity,
        description: "Live system and instance health at a glance.",
        tooltip: "Aggregate CPU/RAM, instance counts, host info", Component: MetricsOverview },
      { id: "health", label: "Health", icon: Heart,
        description: "Real-time diagnostic checks and 1-hour history.",
        tooltip: "Docker, database, routing, disk, and GPU diagnostics", Component: HealthPanel },
      { id: "sessions", label: "Sessions", icon: Terminal,
        description: "Running instances and their lifecycle actions.",
        tooltip: "View and control active instances", Component: MetricsSessions },
      { id: "resources", label: "Resources", icon: Cpu,
        description: "Host resource usage over time.",
        tooltip: "CPU, memory, disk and GPU usage", Component: MetricsResources },
      { id: "logs", label: "Logs", icon: ScrollText,
        description: "Recent system and session events.",
        tooltip: "System event log", Component: MetricsLogs },
    ],
  },
  {
    id: "administration", label: "Administration", icon: Shield, adminOnly: true,
    sections: [
      { id: "users", label: "Users", icon: Users,
        description: "Manage user accounts, roles, and invitations.",
        tooltip: "Create or disable users; generate invites", Component: UsersPanel },
      { id: "workstations", label: "Workstations", icon: MonitorSmartphone,
        description: "Enroll and manage physical Linux machines.",
        tooltip: "Stream physical workstations via the Styx agent", Component: WorkstationsPanel },
      { id: "sso", label: "SSO Providers", icon: KeyRound,
        description: "Configure OIDC / OAuth identity providers.",
        tooltip: "Add and manage single sign-on providers", Component: OAuthProvidersPanel },
      { id: "images", label: "Images", icon: HardDrive,
        description: "Pulled Docker images and cleanup.",
        tooltip: "List and remove cached images", Component: ImageManager },
    ],
  },
  {
    id: "account", label: "Account", icon: UserCircle, adminOnly: false,
    sections: [
      { id: "connected", label: "Connected accounts", icon: Link2,
        description: "Link external sign-in providers to your account.",
        tooltip: "Link or unlink Google, GitHub, and other providers", Component: ConnectedAccounts },
    ],
  },
];

export function visibleCategories(isAdmin: boolean): SettingsCategory[] {
  return CATEGORIES.filter((c) => isAdmin || !c.adminOnly);
}
