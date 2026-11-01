import { render } from "@testing-library/react";
import { useRef } from "react";
import { describe, expect, it, vi } from "vitest";
import { useCanvasEffect } from "../use-canvas-effect";

function Probe({ factory }: { factory: (c: HTMLCanvasElement) => { destroy(): void } | null }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useCanvasEffect(ref, factory, []);
  return <canvas ref={ref} />;
}

describe("useCanvasEffect", () => {
  it("tolerates a factory returning null when getContext is null", () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    const factory = vi.fn((c: HTMLCanvasElement) => (c.getContext("2d") ? { destroy() {} } : null));
    expect(() => render(<Probe factory={factory} />)).not.toThrow();
    expect(factory).toHaveBeenCalledTimes(1);
    expect(factory.mock.results[0]!.value).toBeNull();
  });

  it("destroys on unmount", () => {
    const destroy = vi.fn();
    const { unmount } = render(<Probe factory={() => ({ destroy })} />);
    unmount();
    expect(destroy).toHaveBeenCalledTimes(1);
  });
});
