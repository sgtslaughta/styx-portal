export function LoadError({ retry, className = "text-[13px] text-muted-foreground" }: { retry: () => void; className?: string }) {
  return (
    <p className={className}>
      Couldn&apos;t load — <button type="button" onClick={retry} className="text-primary hover:underline">Retry</button>
    </p>
  );
}
