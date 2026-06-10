import type { Transition, Variants } from "framer-motion";
import { useReducedMotion } from "framer-motion";

/** Calm default spring for layout/position changes. */
export const spring: Transition = { type: "spring", stiffness: 400, damping: 32 };

/** Mount/unmount fade + small slide. Restrained — no scale pop. */
export const fadeSlideIn: Variants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
};

/** Hover lift for cards. */
export const hoverLift = { y: -2 } as const;

/** Stagger children in a list/grid. */
export const listStagger: Variants = {
  animate: { transition: { staggerChildren: 0.03 } },
};

/** Entrance variants that collapse to instant (no transform/opacity animation)
 *  when the user prefers reduced motion. */
export function useFadeSlideIn(): Variants {
  const reduce = useReducedMotion();
  if (reduce) {
    return { initial: { opacity: 1 }, animate: { opacity: 1 }, exit: { opacity: 1 } };
  }
  return fadeSlideIn;
}
