import { render, screen } from "@testing-library/react";
import { test, expect, vi } from "vitest";
import { WorkstationList } from "../workstation-list";
import type { Workstation } from "@/api/client";

const row = {
  id: "w9", name: "Studio", hostname: "h", status: "online", os_info: {}, icon_kind: "emoji",
  icon_etag: "e1", in_use: false, in_use_self: false, in_use_by: null, last_heartbeat: null,
  last_error: null, stream_settings: {}, gpu_info: {},
} as unknown as Workstation;

vi.mock("@/api/client", () => ({
  api: { myWorkstations: () => Promise.resolve([row]) },
  ApiError: class extends Error {},
}));

test("tile renders icon img with etag cache-buster", async () => {
  const { container } = render(<WorkstationList />);
  await screen.findByText("Studio");
  const img = container.querySelector('img[src^="/api/workstations/w9/icon"]')!;
  expect(img.getAttribute("src")).toBe("/api/workstations/w9/icon?v=e1");
  expect(img.getAttribute("alt")).toBe("");
});
