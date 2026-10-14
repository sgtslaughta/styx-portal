import { act, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
vi.mock("@/components/effects/wave-transition", () => ({
  WaveTransition: ({ label }: { label: string }) => <p>{label}</p>,
}));
import { ConnectingPage } from "../ConnectingPage";

const replace = vi.fn();
function at(hash: string) {
  Object.defineProperty(window, "location", { configurable: true,
    value: { origin: "http://localhost", hash, replace } });
}
const enc = (o: object) => "#" + encodeURIComponent(JSON.stringify(o));
afterEach(() => { replace.mockReset(); vi.useRealTimers(); });

test("label-only hash waits, then navigates when the url arrives", () => {
  vi.useFakeTimers();
  at(enc({ label: "Connecting to Box…" }));
  render(<ConnectingPage />);
  expect(screen.getByText("Connecting to Box…")).toBeInTheDocument();
  act(() => { vi.advanceTimersByTime(5000); });
  expect(replace).not.toHaveBeenCalled();
  at(enc({ url: "/w/box/", label: "Connecting to Box…" }));
  act(() => { window.dispatchEvent(new HashChangeEvent("hashchange")); });
  act(() => { vi.advanceTimersByTime(2000); });
  expect(replace).toHaveBeenCalledWith("/w/box/");
});

test("cross-origin url is rejected", () => {
  at(enc({ url: "https://evil.test/x", label: "x" }));
  render(<ConnectingPage />);
  expect(screen.getByText("Invalid connection link.")).toBeInTheDocument();
});
