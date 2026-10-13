/** Styx identity (spec §7). globals.css must use exactly these values. */
export const TOKENS = {
  light: { background: "#EDF1EF", foreground: "#0F1C22", card: "#F7F9F8", muted: "#DFE6E3",
    mutedForeground: "#4A5A60", border: "#C9D3D0", primary: "#2A767C", primaryForeground: "#F7F9F8",
    destructive: "#B8432A", success: "#4F9A6C", successForeground: "#3A7A53",
    obol: "#B88A3E", obolForeground: "#86601F", warningForeground: "#86601F", ring: "#2A767C" },
  dark: { background: "#0F1C22", foreground: "#EDF1EF", card: "#15262D", muted: "#1D3139",
    mutedForeground: "#9FB0B4", border: "#2A4049", primary: "#6FB7BC", primaryForeground: "#0F1C22",
    destructive: "#E07A5F", success: "#4F9A6C", successForeground: "#7CC49A",
    obol: "#B88A3E", obolForeground: "#D2A657", warningForeground: "#D2A657", ring: "#6FB7BC" },
} as const;

/** [fg, bg, label] pairs that carry text. */
export const TEXT_PAIRS: [string, string, string][] = [
  [TOKENS.light.foreground, TOKENS.light.background, "light body"],
  [TOKENS.light.mutedForeground, TOKENS.light.background, "light muted"],
  [TOKENS.light.mutedForeground, TOKENS.light.card, "light muted on card"],
  [TOKENS.light.primaryForeground, TOKENS.light.primary, "light button"],
  [TOKENS.light.primary, TOKENS.light.background, "light link"],
  [TOKENS.light.destructive, TOKENS.light.background, "light danger"],
  [TOKENS.light.obolForeground, TOKENS.light.background, "light obol text"],
  [TOKENS.light.successForeground, TOKENS.light.background, "light ok text"],
  [TOKENS.light.warningForeground, TOKENS.light.card, "light warning text on card"],
  [TOKENS.light.warningForeground, TOKENS.light.background, "light warning text"],
  [TOKENS.dark.warningForeground, TOKENS.dark.card, "dark warning text on card"],
  [TOKENS.dark.warningForeground, TOKENS.dark.background, "dark warning text"],
  [TOKENS.dark.foreground, TOKENS.dark.background, "dark body"],
  [TOKENS.dark.mutedForeground, TOKENS.dark.card, "dark muted on card"],
  [TOKENS.dark.primaryForeground, TOKENS.dark.primary, "dark button"],
  [TOKENS.dark.primary, TOKENS.dark.background, "dark primary text"],
  [TOKENS.dark.ring, TOKENS.dark.background, "dark link"],
  [TOKENS.dark.destructive, TOKENS.dark.background, "dark danger"],
  [TOKENS.dark.obolForeground, TOKENS.dark.background, "dark obol text"],
  [TOKENS.dark.successForeground, TOKENS.dark.background, "dark ok text"],
];

const lum = (hex: string) => {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0]! + 0.7152 * c[1]! + 0.0722 * c[2]!;
};
export const contrast = (a: string, b: string) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x! + 0.05) / (y! + 0.05);
};
