import { createContext, useCallback, useContext, useRef, useState } from "react";
import { WaveTransition } from "./wave-transition";

interface TransitionApi {
  /** Play the liquid wave wipe with an optional caption (e.g. "Connecting…"). */
  play: (label?: string) => void;
}

const Ctx = createContext<TransitionApi | null>(null);

/**
 * Mounts a single global {@link WaveTransition} overlay and exposes `play()`
 * so any screen can trigger the launch/connect wipe without prop drilling.
 */
export function WaveTransitionProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<{ show: boolean; label?: string }>({ show: false });
  // Guards against re-triggering mid-animation (double clicks / StrictMode).
  const busy = useRef(false);

  const play = useCallback((label?: string) => {
    if (busy.current) return;
    busy.current = true;
    setState({ show: true, label });
  }, []);

  const onDone = useCallback(() => {
    busy.current = false;
    setState((s) => ({ ...s, show: false }));
  }, []);

  return (
    <Ctx.Provider value={{ play }}>
      {children}
      <WaveTransition show={state.show} label={state.label} onDone={onDone} />
    </Ctx.Provider>
  );
}

/** Access the global wave transition. No-op if no provider is mounted. */
export function useWaveTransition(): TransitionApi {
  const ctx = useContext(Ctx);
  return ctx ?? { play: () => {} };
}
