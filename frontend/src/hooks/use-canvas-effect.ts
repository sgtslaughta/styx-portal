import { useEffect, type DependencyList, type RefObject } from "react";

/** Mounts a canvas effect; factory may return null (e.g. no canvas context). Destroyed on unmount/deps change. */
export function useCanvasEffect(
  ref: RefObject<HTMLCanvasElement | null>,
  factory: (canvas: HTMLCanvasElement) => { destroy(): void } | null,
  deps: DependencyList,
) {
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const fx = factory(canvas);
    return () => fx?.destroy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
