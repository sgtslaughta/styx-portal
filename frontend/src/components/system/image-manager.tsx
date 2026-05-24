import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Trash2, HardDrive, AlertTriangle } from "lucide-react";
import { useImages, useDeleteImage, usePurgeImages } from "@/hooks/use-images";
import { toast } from "sonner";

function formatSize(mb: number | null) {
  if (mb === null) return "—";
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb} MB`;
}

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function ImageManager() {
  const { data: images, isLoading } = useImages();
  const deleteMut = useDeleteImage();
  const purgeMut = usePurgeImages();
  const [confirmPurge, setConfirmPurge] = useState(false);

  const totalSize = images?.reduce((sum, img) => sum + (img.size_mb ?? 0), 0) ?? 0;

  function handleDelete(id: string, name: string) {
    deleteMut.mutate(id, {
      onSuccess: () => toast.success(`Removed ${name}`),
      onError: (e) => toast.error(e.message),
    });
  }

  function handlePurge() {
    purgeMut.mutate(undefined, {
      onSuccess: () => { toast.success("Unused images purged"); setConfirmPurge(false); },
      onError: (e) => toast.error(e.message),
    });
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => (
          <motion.div key={i} className="h-14 rounded-lg bg-card" animate={{ opacity: [0.3, 0.6, 0.3] }} transition={{ duration: 1.5, repeat: Infinity, delay: i * 0.15 }} />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <HardDrive className="h-5 w-5 text-muted-foreground" />
          <div>
            <h3 className="text-sm font-medium">Docker Images</h3>
            <p className="text-xs text-muted-foreground">
              {images?.length ?? 0} image{images?.length !== 1 ? "s" : ""} · {formatSize(totalSize)} total
            </p>
          </div>
        </div>

        {images && images.length > 0 && (
          <div className="flex items-center gap-2">
            {confirmPurge ? (
              <motion.div initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} className="flex items-center gap-2">
                <span className="text-xs text-amber-400">Remove all unused?</span>
                <button onClick={handlePurge} disabled={purgeMut.isPending} className="rounded-md bg-red-500/20 px-3 py-1 text-xs font-medium text-red-400 hover:bg-red-500/30 transition-colors">
                  {purgeMut.isPending ? "Purging…" : "Confirm"}
                </button>
                <button onClick={() => setConfirmPurge(false)} className="rounded-md px-2 py-1 text-xs text-muted-foreground hover:text-foreground transition-colors">
                  Cancel
                </button>
              </motion.div>
            ) : (
              <button onClick={() => setConfirmPurge(true)} className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground hover:text-red-400 hover:border-red-500/40 transition-colors">
                <Trash2 className="h-3 w-3" />
                Purge Unused
              </button>
            )}
          </div>
        )}
      </div>

      {/* Image list */}
      {!images?.length ? (
        <div className="rounded-lg border border-border bg-card/50 py-12 text-center">
          <HardDrive className="mx-auto mb-2 h-8 w-8 text-muted-foreground/40" />
          <p className="text-sm text-muted-foreground">No pulled images tracked yet</p>
          <p className="text-xs text-muted-foreground/60">Images appear here when you launch instances</p>
        </div>
      ) : (
        <div className="space-y-1.5">
          <AnimatePresence mode="popLayout">
            {images.map((img) => (
              <motion.div
                key={img.id}
                layout
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="group flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-3 transition-colors hover:border-border/80"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-mono text-foreground">{img.image}</p>
                  <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                    <span>{formatSize(img.size_mb)}</span>
                    <span>Pulled {timeAgo(img.pulled_at)}</span>
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(img.id, img.image)}
                  disabled={deleteMut.isPending}
                  className="rounded-md p-1.5 text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-red-400 hover:bg-red-500/10 transition-all"
                  title="Remove image"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* Warning */}
      {images && images.length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500/60" />
          <p className="text-[11px] text-amber-400/80">
            Images in use by instances cannot be removed. Destroy all instances using an image first.
          </p>
        </div>
      )}
    </div>
  );
}
