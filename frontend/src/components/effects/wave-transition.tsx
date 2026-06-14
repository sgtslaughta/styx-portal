import { AnimatePresence, motion, useReducedMotion } from "framer-motion";

/* Styx wave glyph paths (lucide "Waves"), inlined so each stroke can draw/flow. */
const WAVE_PATHS = [
  "M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1",
  "M2 12c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1",
  "M2 18c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1",
];

/* Wavy top edge of the rising liquid — morphs between two crests for flow. */
const CREST_A = "M0,16 Q150,2 300,16 T600,16 L600,40 L0,40 Z";
const CREST_B = "M0,16 Q150,30 300,16 T600,16 L600,40 L0,40 Z";

export interface WaveTransitionProps {
  show: boolean;
  label?: string;
  /** Fired when the full sweep finishes; provider clears state here. */
  onDone: () => void;
}

/**
 * Full-screen "liquid wave wipe": a brand-blue tide rises to cover the viewport
 * while the Styx wave glyph draws + bobs at center, then the tide recedes,
 * revealing whatever changed beneath. ~1.3s, decorative (aria-hidden).
 */
export function WaveTransition({ show, label, onDone }: WaveTransitionProps) {
  const reduce = useReducedMotion();

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          key="wave-transition"
          aria-hidden="true"
          className="pointer-events-none fixed inset-0 z-[100] overflow-hidden"
          initial={{ opacity: 0 }}
          animate={
            reduce
              ? { opacity: [0, 1, 1, 0] }
              : { opacity: [0, 1, 1, 1, 0] }
          }
          exit={{ opacity: 0 }}
          transition={
            reduce
              ? { duration: 0.6, times: [0, 0.25, 0.7, 1] }
              : { duration: 1.3, times: [0, 0.15, 0.6, 0.85, 1] }
          }
          onAnimationComplete={onDone}
          style={{
            // brand-tinted dim behind the tide
            background:
              "radial-gradient(circle at 50% 45%, rgba(20,40,90,0.45), rgba(8,16,32,0.78))",
            backdropFilter: "blur(3px)",
          }}
        >
          {/* Rising / receding liquid tide */}
          {!reduce && (
            <motion.div
              className="absolute inset-x-0 bottom-0"
              initial={{ height: "0%" }}
              animate={{ height: ["0%", "108%", "108%", "0%"] }}
              transition={{
                duration: 1.3,
                times: [0, 0.32, 0.6, 1],
                ease: [0.65, 0, 0.35, 1],
              }}
              style={{
                background:
                  "linear-gradient(180deg, var(--brand-accent, #2f6fe0) 0%, #16284f 70%, #0c1730 100%)",
              }}
            >
              {/* crest sitting on top of the tide */}
              <svg
                className="absolute left-0 right-0 top-0 w-full"
                style={{ transform: "translateY(-98%)" }}
                viewBox="0 0 600 40"
                height="40"
                preserveAspectRatio="none"
              >
                <motion.path
                  fill="var(--brand-accent, #2f6fe0)"
                  initial={{ d: CREST_A }}
                  animate={{ d: [CREST_A, CREST_B, CREST_A] }}
                  transition={{ duration: 1.1, repeat: Infinity, ease: "easeInOut" }}
                />
              </svg>
            </motion.div>
          )}

          {/* Center glyph + label */}
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4">
            <motion.svg
              width="96"
              height="96"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#ffffff"
              strokeWidth={1.6}
              strokeLinecap="round"
              strokeLinejoin="round"
              initial={{ opacity: 0, scale: reduce ? 1 : 0.6 }}
              animate={
                reduce
                  ? { opacity: [0, 1, 1, 0] }
                  : { opacity: [0, 1, 1, 0], scale: [0.6, 1, 1, 1.06], y: [4, -3, -3, 4] }
              }
              transition={{
                duration: reduce ? 0.6 : 1.3,
                times: [0, 0.34, 0.66, 1],
                ease: "easeInOut",
              }}
              style={{ filter: "drop-shadow(0 4px 14px rgba(0,0,0,0.35))" }}
            >
              {WAVE_PATHS.map((d, i) => (
                <motion.path
                  key={i}
                  d={d}
                  initial={{ pathLength: reduce ? 1 : 0 }}
                  animate={{ pathLength: 1 }}
                  transition={{
                    duration: 0.5,
                    delay: reduce ? 0 : 0.12 + i * 0.12,
                    ease: "easeInOut",
                  }}
                />
              ))}
            </motion.svg>

            {label && (
              <motion.p
                className="text-sm font-medium tracking-wide text-white/90"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: [0, 1, 1, 0], y: [6, 0, 0, 0] }}
                transition={{
                  duration: reduce ? 0.6 : 1.3,
                  times: [0, 0.4, 0.7, 1],
                }}
              >
                {label}
              </motion.p>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
