/** Chart/sparkline series colors. Reference CSS vars from globals.css so they follow the theme. */
export const CHART_PALETTE = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
] as const;

export const CHART_COLORS = {
  cpu: "var(--chart-1)",
  memory: "var(--chart-2)",
  network: "var(--chart-3)",
  storage: "var(--chart-4)",
} as const;
