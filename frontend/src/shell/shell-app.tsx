import { useCallback, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { toTile } from "@/lib/service-tiles";
import { LazyMotion, MotionConfig, domMax } from "framer-motion";
import { Dock } from "./dock";
import { EdgeTab } from "./edge-tab";
import { readPos } from "./ferry-pos";
import { Card, Frame } from "./frame";
import { useHotkey } from "./use-hotkey";
import { parseShellPath } from "./url";

export function ShellApp() {
  // Frozen: URL sync rewrites the address bar, which must not change the iframe src.
  const [target] = useState(() => parseShellPath(location.pathname, location.search, location.hash));
  const { data: tiles, isPending, error, refetch } = useQuery({
    queryKey: ["service-tiles"],
    queryFn: async () => (await api.listServiceTiles()).map(toTile),
    refetchInterval: 30_000,
  });
  const { data: focus } = useQuery({ queryKey: ["service-focus"], queryFn: () => api.serviceFocus() });
  const tabRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [side, setSide] = useState(() => readPos().side);
  const [frameEl, setFrameEl] = useState<HTMLIFrameElement | null>(null);
  const toggle = useCallback(() => { setSide(readPos().side); setOpen((o) => !o); }, []);
  useHotkey(() => [window, frameEl?.contentWindow ?? null], toggle, frameEl, () => setOpen(false));
  const onTitle = useCallback((t: string) => { if (t) document.title = t; }, []);
  if (isPending) return null;
  if (error && !tiles) {
    return <Card title="Couldn't load your apps" text={`${error.message} Check your connection and try again.`}
      action="Try again" onAction={() => void refetch()} />;
  }
  const tile = target && tiles?.find((t) => t.slug === target.slug);
  if (!target || !tile) {
    return <Card title="This app isn't available" text="It may have been removed or turned off."
      href="/_styx/exit?next=/" action="Go home" />;
  }
  return (
    <LazyMotion features={domMax}> {/* domMax: the edge tab needs drag */}
      <MotionConfig reducedMotion="user">
        <div className="h-dvh w-screen">
          <Frame key={tile.slug} tile={tile} inner={target.inner} onTitle={onTitle} onFrame={setFrameEl} />
          <EdgeTab onOpen={toggle} open={open} tabRef={tabRef} />
          <Dock open={open} onOpenChange={setOpen} tiles={tiles} current={tile.slug} focusSlug={focus?.slug ?? null} side={side} tabRef={tabRef} />
        </div>
      </MotionConfig>
    </LazyMotion>
  );
}
