export type Theme = "light" | "dark" | "system";

/** Routes shown to logged-out users, where there is no theme toggle. */
export const PUBLIC_PATHS = ["/login", "/setup", "/accept-invite"];

export function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"));
}

/**
 * Resolve whether the dark class should be applied.
 *
 * Public pages always follow the OS — a logged-out user can't reach the theme
 * toggle, so a stored "dark" preference must not trap them in dark on a light
 * system. Authenticated pages honour the user's stored choice.
 *
 * Pure (no DOM/localStorage access) so it can be unit-tested.
 */
export function resolveDark(
  pathname: string,
  stored: Theme | null,
  systemPrefersDark: boolean,
): boolean {
  const effective: Theme = isPublicPath(pathname) ? "system" : stored ?? "system";
  return effective === "dark" || (effective === "system" && systemPrefersDark);
}
