import { useCallback, useEffect, useRef } from "react";
import { Link, useParams } from "react-router";
import { Loader2 } from "lucide-react";
import { useInstances, useKeepalive } from "@/hooks/use-instances";
import { useTemplates } from "@/hooks/use-templates";
import { startActivityHeartbeat } from "@/lib/activity";
import { startThumbUploader } from "@/lib/stream-thumb";

const ALLOW = "fullscreen; clipboard-read; clipboard-write; autoplay; gamepad; microphone; camera; display-capture; pointer-lock";
const WAITING = ["created", "creating", "pulling", "starting"];

/** Tab icon for a template icon: image URL as-is, emoji drawn into an SVG. */
export function faviconHref(icon: string | null | undefined): string | null {
  if (!icon) return null;
  if (icon.startsWith("http") || icon.startsWith("/")) return icon;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">${icon}</text></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex h-dvh w-screen flex-col items-center justify-center gap-3 bg-black p-4 text-center text-sm text-white/80">
      {children}
    </main>
  );
}

/** Full-viewport same-origin wrapper around /i/<sub>/ so the portal can snapshot the stream for card thumbnails. */
export function DesktopPage() {
  const { sub = "" } = useParams();
  const { data, isPending } = useInstances();
  const instance = data?.find((i) => i.subdomain === sub);
  const keepalive = useKeepalive();
  const frameRef = useRef<HTMLIFrameElement>(null);
  const live = instance?.status === "running" || instance?.status === "idle";
  const id = instance?.id;

  const { data: templates } = useTemplates();
  const icon = faviconHref(templates?.find((t) => t.id === instance?.template_id)?.icon);

  useEffect(() => {
    if (instance?.name) document.title = instance.name;
  }, [instance?.name]);

  useEffect(() => {
    const link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
    if (!link || !icon) return;
    const prev = { href: link.href, type: link.type };
    link.href = icon;
    link.removeAttribute("type");
    return () => { link.href = prev.href; link.type = prev.type; };
  }, [icon]);

  useEffect(() => {
    if (!live || !id) return;
    const stop = startThumbUploader(id, () => frameRef.current);
    const stopBeat = startActivityHeartbeat(id, () => frameRef.current);
    const focus = () => frameRef.current?.focus();
    window.addEventListener("focus", focus);
    return () => { stop(); stopBeat(); window.removeEventListener("focus", focus); };
  }, [live, id]);

  const onLoad = useCallback(() => frameRef.current?.focus(), []);

  if (isPending) return <Notice><Loader2 className="size-5 animate-spin" aria-hidden /></Notice>;
  if (!instance) {
    return <Notice><p>Desktop not found</p><Link to="/" className="underline">Go home</Link></Notice>;
  }
  if (WAITING.includes(instance.status)) {
    return (
      <Notice>
        <Loader2 className="size-5 animate-spin" aria-hidden />
        <p>{instance.status_detail || `${instance.name} is starting…`}</p>
      </Notice>
    );
  }
  if (!live) {
    return <Notice><p>{instance.name} is {instance.status}</p><Link to="/" className="underline">Go home</Link></Notice>;
  }
  return (
    <>
      {instance.status === "idle" && (
        <div role="alert" className="fixed inset-x-0 top-0 z-10 flex items-center justify-center gap-3 bg-amber-500 px-3 py-2 text-sm font-medium text-black">
          Pausing soon due to inactivity
          <button
            type="button"
            className="rounded bg-black/80 px-2 py-0.5 text-white"
            onClick={() => keepalive.mutate(instance.id, { onSettled: () => frameRef.current?.focus() })}
          >
            I'm here
          </button>
        </div>
      )}
    <iframe
      ref={frameRef}
      src={`/i/${sub}/`}
      title={instance.name}
      allow={ALLOW}
      onLoad={onLoad}
      className="block h-screen w-screen border-0 bg-black"
      style={{ width: "100vw", height: "100vh" }}
    />
    </>
  );
}
