import { useState, useRef, useCallback } from "react";
import { motion } from "framer-motion";
import { Star, Download, ExternalLink, Maximize2, Minimize2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SearchSortBar } from "@/components/common/search-sort-bar";
import { useRegistryImages } from "@/hooks/use-registry";
import { isWebUrl } from "@/lib/connect-wipe";
import { RegistryPreviewCard } from "./registry-preview-card";
import type { RegistryImage } from "@/lib/types";

interface RegistryBrowserProps {
  onImport: (image: RegistryImage) => void;
}

const CATEGORIES = ["All", "Productivity", "Network", "Media", "Tools", "DNS", "Web", "Gaming"];

export function RegistryBrowser({ onImport }: RegistryBrowserProps) {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All");
  const { data: images, isLoading, isError } = useRegistryImages({
    category: category === "All" ? undefined : category,
    search: search || undefined,
  });

  return (
    <div>
      <div className="mb-4">
        <SearchSortBar query={search} onQueryChange={setSearch} placeholder="Search images…">
          <div className="flex flex-wrap gap-1">
            {CATEGORIES.map((cat) => (
              <Button key={cat} variant={category === cat ? "default" : "ghost"} size="sm" onClick={() => setCategory(cat)} className="text-xs">
                {cat}
              </Button>
            ))}
          </div>
        </SearchSortBar>
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => <div key={i} className="styx-card h-28 animate-pulse rounded-xl" />)}
        </div>
      )}

      {isError && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-center text-sm text-destructive">
          Could not load LinuxServer registry.
        </div>
      )}

      {images && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {images.map((img) => (
            <RegistryCard key={img.name} image={img} onImport={onImport} />
          ))}
        </div>
      )}

      {images && images.length === 0 && (
        <p className="py-8 text-center text-sm text-muted-foreground">No images match your search.</p>
      )}
    </div>
  );
}

function RegistryCard({ image: img, onImport }: { image: RegistryImage; onImport: (img: RegistryImage) => void }) {
  const [showPreview, setShowPreview] = useState(false);
  const [previewPos, setPreviewPos] = useState({ x: 0, y: 0 });
  const [spinIcon, setSpinIcon] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const hasHoveredRef = useRef(false);
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dismissTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function cancelDismiss() {
    if (dismissTimer.current) { clearTimeout(dismissTimer.current); dismissTimer.current = null; }
  }

  const handleMouseEnter = useCallback(() => {
    cancelDismiss();
    if (!hasHoveredRef.current) {
      hasHoveredRef.current = true;
      setSpinIcon(true);
      setTimeout(() => setSpinIcon(false), 600);
    }
    hoverTimer.current = setTimeout(() => setShowPreview(true), 800);
  }, []);

  function handleMouseMove(e: React.MouseEvent) {
    if (!showPreview) {
      setPreviewPos({
        x: Math.min(e.clientX + 16, window.innerWidth - 520),
        y: Math.max(8, Math.min(e.clientY - 200, window.innerHeight - 480)),
      });
    }
  }

  function scheduleDismiss() {
    cancelDismiss();
    dismissTimer.current = setTimeout(() => {
      setShowPreview(false);
      setExpanded(false);
    }, 300);
  }

  function handleMouseLeave() {
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
    scheduleDismiss();
  }

  return (
    <div
      className="styx-card group relative flex cursor-pointer items-start gap-3 rounded-xl p-3 transition-colors hover:border-primary/50"
      onClick={() => onImport(img)}
      onMouseEnter={handleMouseEnter}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
    >
      <motion.img
        src={img.project_logo}
        alt={img.name}
        className="h-10 w-10 rounded-md object-contain"
        animate={spinIcon ? { rotate: 360, scale: [1, 1.2, 1] } : { rotate: 0 }}
        transition={spinIcon ? { duration: 0.6, ease: "easeOut" } : { duration: 0 }}
        onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
      />
      <div className="flex-1 overflow-hidden">
        <h4 className="truncate text-sm font-semibold">{img.name}</h4>
        <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">{img.description}</p>
        <div className="mt-2 flex items-center gap-3 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1"><Star className="h-3 w-3" /> {img.stars}</span>
          <span className="flex items-center gap-1"><Download className="h-3 w-3" /> {(img.monthly_pulls / 1000).toFixed(0)}k/mo</span>
          {img.category && <Badge variant="outline" className="text-[10px] px-1 py-0">{img.category}</Badge>}
          {img.github_url && (
            <a href={img.github_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="flex items-center gap-0.5 hover:text-foreground">
              <ExternalLink className="h-2.5 w-2.5" /> GitHub
            </a>
          )}
          {isWebUrl(img.project_url) && (
            <a href={img.project_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="flex items-center gap-0.5 hover:text-foreground">
              <ExternalLink className="h-2.5 w-2.5" /> Site
            </a>
          )}
        </div>
        {img.version && <div className="mt-1 text-[10px] text-muted-foreground/60">{img.version}</div>}
      </div>

      {showPreview && (
        <div
          role="dialog"
          aria-label={`${img.name} details`}
          className="styx-card fixed z-50 overflow-hidden rounded-lg shadow-2xl"
          style={{
            left: expanded ? Math.min(previewPos.x, window.innerWidth - 770) : previewPos.x,
            top: previewPos.y,
            width: expanded ? 750 : 500,
          }}
          onMouseEnter={cancelDismiss}
          onMouseLeave={scheduleDismiss}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-end border-b border-border px-3 py-1.5">
            <button
              className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
              onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}
              title={expanded ? "Shrink" : "Expand"}
              aria-label={expanded ? "Shrink preview" : "Expand preview"}
            >
              {expanded ? <Minimize2 className="h-3 w-3" /> : <Maximize2 className="h-3 w-3" />}
            </button>
          </div>
          <RegistryPreviewCard image={img} />
        </div>
      )}
    </div>
  );
}
