const CLOUDFLARE = ["CLOUDFLARE_TURN_TOKEN_ID", "CLOUDFLARE_TURN_API_TOKEN"];
const GENERIC = [
  "TURN_HOST",
  "TURN_PORT",
  "TURN_PROTOCOL",
  "TURN_TLS",
  "TURN_SHARED_SECRET",
  "TURN_USERNAME",
  "TURN_PASSWORD",
];

/** Whether a setting row should be shown given the chosen TURN provider. */
export function isSettingVisible(key: string, provider: unknown): boolean {
  if (CLOUDFLARE.includes(key)) return provider === "cloudflare";
  if (GENERIC.includes(key)) return provider === "generic";
  return true;
}
