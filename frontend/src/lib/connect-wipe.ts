/**
 * Open a session (instance / workstation) in a new tab that first plays the
 * Styx wave wipe, then hands off to the real URL. The interstitial lives at
 * `/connecting`; payload rides in the URL hash so it's stateless and immune to
 * cross-tab storage races. Called synchronously inside a click handler so the
 * popup is never blocked.
 */
export function openConnectWipe(url: string, label: string): void {
  const payload = encodeURIComponent(JSON.stringify({ url, label }));
  window.open(`/connecting#${payload}`, "_blank", "noopener");
}
