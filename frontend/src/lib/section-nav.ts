/** Opens an admin settings section (SettingsLayout listens for this event). */
export const SECTION_EVENT = "styx:settings-section";
export const goSection = (id: string) => window.dispatchEvent(new CustomEvent(SECTION_EVENT, { detail: id }));
