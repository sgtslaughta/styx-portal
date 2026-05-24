import { useInstances } from "@/hooks/use-instances";
import { InstanceCard } from "./instance-card";
import type { Instance } from "@/lib/types";

interface InstanceGridProps {
  onSelect: (instance: Instance) => void;
  onLaunch: () => void;
}

export function InstanceGrid({ onSelect, onLaunch }: InstanceGridProps) {
  const { data: instances, isLoading, isError } = useInstances();

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="aspect-[4/3] animate-pulse rounded-xl bg-card" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-center text-sm text-destructive">
        Backend unavailable — retrying...
      </div>
    );
  }

  if (!instances?.length) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <p className="mb-1 text-lg font-medium text-foreground">No instances yet</p>
        <p className="mb-4 text-sm text-muted-foreground">
          Browse the Template Gallery to launch one.
        </p>
        <button onClick={onLaunch} className="text-sm font-medium text-primary hover:underline">
          Go to Template Gallery &rarr;
        </button>
      </div>
    );
  }

  const domain = window.location.hostname === "localhost"
    ? "localhost"
    : window.location.hostname.split(".").slice(1).join(".");

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      {instances.map((instance) => (
        <InstanceCard key={instance.id} instance={instance} domain={domain} onSelect={onSelect} />
      ))}
    </div>
  );
}
