import { render, screen } from "@testing-library/react";
import { test, expect, vi } from "vitest";
import { WorkstationPreview } from "../workstation-list";
import type { Workstation } from "@/api/client";

const row = {
  id: "w9", name: "Studio", hostname: "h", status: "online", os_info: {}, icon_kind: "emoji",
  icon_etag: "e1", in_use: false, in_use_self: false, in_use_by: null, last_heartbeat: null,
  last_error: null, stream_settings: {}, gpu_info: {},
} as unknown as Workstation;

vi.mock("@/api/client", () => ({
  api: { workstationThumbUrl: (id: string) => `/api/workstations/${id}/thumbnail` },
  ApiError: class extends Error {},
}));

test("preview shows name and thumbnail", () => {
  const { container } = render(<WorkstationPreview ws={row} />);
  expect(screen.getByText("Studio")).toBeTruthy();
  expect(container.querySelector('img[src="/api/workstations/w9/thumbnail?t=0"]')).not.toBeNull();
});
