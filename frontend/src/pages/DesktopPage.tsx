import { useCallback, useEffect, useRef } from "react";
import { Link, useParams } from "react-router";
import { Loader2 } from "lucide-react";
import { useInstances } from "@/hooks/use-instances";
import { startThumbUploader } from "@/lib/stream-thumb";

const ALLOW = "fullscreen; clipboard-read; clipboard-write; autoplay; gamepad; microphone; camera; display-capture; pointer-lock";
const WAITING = ["created", "creating", "pulling", "starting"];

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
  const frameRef = useRef<HTMLIFrameElement>(null);
  const live = instance?.status === "running" || instance?.status === "idle";
  const id = instance?.id;

  useEffect(() => {
    if (instance?.name) document.title = instance.name;
  }, [instance?.name]);

  useEffect(() => {
    if (!live || !id) return;
    const stop = startThumbUploader(id, () => frameRef.current);
    const focus = () => frameRef.current?.focus();
    window.addEventListener("focus", focus);
    return () => { stop(); window.removeEventListener("focus", focus); };
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
    <iframe
      ref={frameRef}
      src={`/i/${sub}/`}
      title={instance.name}
      allow={ALLOW}
      onLoad={onLoad}
      className="block h-screen w-screen border-0 bg-black"
      style={{ width: "100vw", height: "100vh" }}
    />
  );
}
