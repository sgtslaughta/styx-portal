import { useState, useRef } from "react";
import { Search, Star, Download, ExternalLink } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useRegistryImages } from "@/hooks/use-registry";
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
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input placeholder="Search images..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9" />
        </div>
        <div className="flex gap-1 flex-wrap">
          {CATEGORIES.map((cat) => (
            <Button key={cat} variant={category === cat ? "default" : "ghost"} size="sm" onClick={() => setCategory(cat)} className="text-xs">
              {cat}
            </Button>
          ))}
        </div>
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => <div key={i} className="h-28 animate-pulse rounded-xl bg-card" />)}
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
  const [previewReady, setPreviewReady] = useState(false);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const loadTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function handleMouseEnter() {
    if (img.project_url) {
      hoverTimer.current = setTimeout(() => setShowPreview(true), 800);
    }
  }

  function handleMouseMove(e: React.MouseEvent) {
    setMousePos({ x: e.clientX, y: e.clientY });
  }

  function handleMouseLeave() {
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
    if (loadTimer.current) clearTimeout(loadTimer.current);
    setShowPreview(false);
    setPreviewReady(false);
  }

  function handleIframeLoad() {
    loadTimer.current = setTimeout(() => setPreviewReady(true), 300);
  }

  function handleIframeError() {
    setShowPreview(false);
    setPreviewReady(false);
  }

  return (
    <div
      className="group relative flex cursor-pointer items-start gap-3 rounded-xl border border-border bg-card p-3 transition-colors hover:border-primary/50"
      onClick={() => onImport(img)}
      onMouseEnter={handleMouseEnter}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
    >
      <img src={img.project_logo} alt={img.name} className="h-10 w-10 rounded-md object-contain" onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
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
          {img.project_url && (
            <a href={img.project_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="flex items-center gap-0.5 hover:text-foreground">
              <ExternalLink className="h-2.5 w-2.5" /> Site
            </a>
          )}
        </div>
        {img.version && <div className="mt-1 text-[10px] text-muted-foreground/60">{img.version}</div>}
      </div>

      {showPreview && img.project_url && (
        <div
          className={`fixed z-50 overflow-hidden rounded-lg border border-border bg-card shadow-2xl transition-opacity duration-150 ${previewReady ? "opacity-100" : "opacity-0 pointer-events-none"}`}
          style={{
            left: Math.min(mousePos.x + 16, window.innerWidth - 520),
            top: Math.min(mousePos.y - 200, window.innerHeight - 420),
            width: 500,
            height: 400,
          }}
          onClick={(e) => { e.stopPropagation(); window.open(img.project_url, "_blank"); }}
        >
          <div className="flex items-center justify-between border-b border-border px-3 py-1.5 cursor-pointer">
            <span className="text-[10px] text-muted-foreground truncate">{img.project_url}</span>
            <ExternalLink className="h-3 w-3 flex-shrink-0 text-muted-foreground" />
          </div>
          <iframe
            src={img.project_url}
            className="h-[calc(100%-28px)] w-full"
            sandbox="allow-scripts allow-same-origin"
            title={`${img.name} preview`}
            onLoad={handleIframeLoad}
            onError={handleIframeError}
          />
        </div>
      )}
    </div>
  );
}
