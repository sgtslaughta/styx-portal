import { createContext, useContext } from "react";

/** False while the admin tab is hidden (SettingsLayout stays mounted to keep unsaved edits). */
export const AdminActiveContext = createContext(true);

/** Poll interval for admin-only queries: `ms` while the admin tab is visible, otherwise off. */
export function useAdminPoll(ms: number): number | false {
  return useContext(AdminActiveContext) ? ms : false;
}
