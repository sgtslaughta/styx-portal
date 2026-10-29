import { Star, Download, ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { isWebUrl, openExternal } from "@/lib/connect-wipe";
import type { RegistryImage } from "@/lib/types";

/** Info card shown on registry hover (external sites can't be framed: CSP + XFO). */
export function RegistryPreviewCard({ image: img }: { image: RegistryImage }) {
  const changelog = (img.changelog ?? []).slice(0, 2);
  const tags = img.tags.slice(0, 3);
  return (
    <div className="flex max-h-[420px] flex-col gap-2 overflow-y-auto p-3 text-xs">
      <div className="flex items-center gap-2">
        <img src={img.project_logo} alt="" className="h-10 w-10 rounded-md object-contain" onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
        <div className="min-w-0 flex-1">
          <h4 className="truncate text-sm font-semibold">{img.name}</h4>
          <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
            {img.version && <span>{img.version}</span>}
            {img.stable && <Badge variant="outline" className="px-1 py-0 text-[10px]">stable</Badge>}
          </div>
        </div>
        {img.category && <Badge variant="outline" className="px-1 py-0 text-[10px]">{img.category}</Badge>}
      </div>
      <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
        <span className="flex items-center gap-1"><Star className="h-3 w-3" /> {img.stars}</span>
        <span className="flex items-center gap-1"><Download className="h-3 w-3" /> {(img.monthly_pulls / 1000).toFixed(0)}k/mo</span>
      </div>
      <p className="max-h-32 overflow-y-auto whitespace-pre-line text-muted-foreground">{img.description}</p>
      {img.architectures.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {img.architectures.map((a) => <Badge key={a.arch} variant="secondary" className="px-1 py-0 text-[10px]">{a.arch}</Badge>)}
        </div>
      )}
      {tags.length > 0 && (
        <ul className="space-y-0.5 text-[11px]">
          {tags.map((t) => <li key={t.tag}><span className="font-mono">{t.tag}</span> — <span className="text-muted-foreground">{t.desc}</span></li>)}
        </ul>
      )}
      {changelog.length > 0 && (
        <ul className="space-y-0.5 text-[11px] text-muted-foreground">
          {changelog.map((c) => <li key={`${c.date}-${c.desc}`}>{c.date} — {c.desc}</li>)}
        </ul>
      )}
      {img.config.application_setup && (
        <details className="text-[11px]">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Setup notes</summary>
          <pre className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap font-sans text-muted-foreground">{img.config.application_setup}</pre>
        </details>
      )}
      <div className="flex gap-2 border-t border-border pt-2">
        {isWebUrl(img.project_url) && (
          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={(e) => { e.stopPropagation(); openExternal(img.project_url); }}>
            <ExternalLink className="mr-1 h-3 w-3" /> Open site
          </Button>
        )}
        {img.github_url && (
          <Button size="sm" variant="outline" className="h-7 text-xs" asChild>
            <a href={img.github_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
              <ExternalLink className="mr-1 h-3 w-3" /> GitHub
            </a>
          </Button>
        )}
      </div>
    </div>
  );
}
