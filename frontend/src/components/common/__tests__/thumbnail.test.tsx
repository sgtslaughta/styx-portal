import { act, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { Thumbnail } from "../thumbnail";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

test("shows the shot and shows the icon fallback on error", () => {
  const { container } = render(<Thumbnail src="/api/x/thumbnail" icon="🖥️" />);
  const img = container.querySelector('img[alt="Live preview"]')!;
  expect(img.getAttribute("src")).toBe("/api/x/thumbnail?t=0");
  expect(img.className).toContain("opacity-0");
  fireEvent.load(img);
  expect(img.className).toContain("opacity-100");
  fireEvent.error(img);
  expect(img.className).toContain("opacity-0");
});

test("refreshes every 60s by default", () => {
  const { container } = render(<Thumbnail src="/a" icon={null} />);
  act(() => { vi.advanceTimersByTime(60000); });
  expect(container.querySelector('img[alt="Live preview"]')!.getAttribute("src")).toBe("/a?t=1");
});

test("no image request and no refresh button when not live", () => {
  const { container, queryByRole } = render(<Thumbnail src="/a" icon={null} isLive={false} onRefresh={async () => {}} />);
  expect(container.querySelector('img[alt="Live preview"]')).toBeNull();
  expect(queryByRole("button")).toBeNull();
});

test("refresh button only with onRefresh", () => {
  const { queryByRole, rerender } = render(<Thumbnail src="/a" icon={null} />);
  expect(queryByRole("button")).toBeNull();
  rerender(<Thumbnail src="/a" icon={null} onRefresh={async () => {}} />);
  expect(queryByRole("button", { name: "Refresh preview" })).not.toBeNull();
});
