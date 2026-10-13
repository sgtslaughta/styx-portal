import { useCallback, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { toTile } from "@/lib/service-tiles";
import { Card, Frame } from "./frame";
import { parseShellPath } from "./url";

export function ShellApp() {
  // Frozen: URL sync rewrites the address bar, which must not change the iframe src.
  const [target] = useState(() => parseShellPath(location.pathname, location.search, location.hash));
  const { data: tiles, isPending, error, refetch } = useQuery({
    queryKey: ["service-tiles"],
    queryFn: async () => (await api.listServiceTiles()).map(toTile),
  });
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
    <div className="h-dvh w-screen">
      <Frame key={tile.slug} tile={tile} inner={target.inner} onTitle={onTitle} />
    </div>
  );
}
