import { ExternalLink, Github, BookOpen } from "lucide-react";
import type { RegistryImage } from "@/lib/types";

interface RegistryInfoProps {
  image: RegistryImage;
}

export function RegistryInfo({ image }: RegistryInfoProps) {
  return (
    <div className="space-y-3 rounded-lg border border-border bg-card/50 p-3">
      {/* Header: logo + name + version */}
      <div className="flex items-start gap-3">
        {image.project_logo && (
          <img src={image.project_logo} alt={image.name} className="h-12 w-12 rounded-lg bg-background object-cover" />
        )}
        <div className="min-w-0 flex-1">
          <div className="font-semibold text-sm">{image.name}</div>
          {image.tags && image.tags.length > 0 && (
            <div className="text-xs text-muted-foreground">{image.tags[0]?.tag}</div>
          )}
          {image.category && (
            <div className="mt-1 inline-block rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
              {image.category}
            </div>
          )}
        </div>
      </div>

      {/* Stats: stars/pulls */}
      {(image.stars != null || image.monthly_pulls != null) && (
        <div className="flex gap-4 text-xs text-muted-foreground">
          {image.stars != null && <span>⭐ {image.stars.toLocaleString()}</span>}
          {image.monthly_pulls != null && <span>📥 {image.monthly_pulls.toLocaleString()}</span>}
        </div>
      )}

      {/* Description */}
      {image.description && (
        <p className="text-xs text-muted-foreground leading-relaxed">{image.description}</p>
      )}

      {/* Links */}
      <div className="flex flex-wrap gap-2">
        {image.github_url && (
          <a href={image.github_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 rounded-md bg-secondary px-2 py-1 text-xs hover:bg-secondary/80 transition-colors">
            <Github className="h-3 w-3" />
            GitHub
            <ExternalLink className="h-3 w-3" />
          </a>
        )}
        {image.project_url && (
          <a href={image.project_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 rounded-md bg-secondary px-2 py-1 text-xs hover:bg-secondary/80 transition-colors">
            <BookOpen className="h-3 w-3" />
            Project
            <ExternalLink className="h-3 w-3" />
          </a>
        )}
        {image.config?.application_setup && (
          <a href={image.project_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 rounded-md bg-secondary px-2 py-1 text-xs hover:bg-secondary/80 transition-colors">
            <BookOpen className="h-3 w-3" />
            Setup
            <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </div>

      {/* Collapsible changelog */}
      {image.changelog && image.changelog.length > 0 && (
        <details className="group cursor-pointer">
          <summary className="text-xs font-medium text-muted-foreground select-none">Changelog</summary>
          <div className="mt-2 space-y-1 max-h-32 overflow-y-auto">
            {image.changelog.map((entry, i) => (
              <div key={i} className="text-[10px] text-muted-foreground">
                <span className="font-mono text-foreground">{entry.date}</span> — {entry.desc}
              </div>
            ))}
          </div>
        </details>
      )}

      {/* Environment vars doc list */}
      {image.config?.env_vars && image.config.env_vars.length > 0 && (
        <details className="group cursor-pointer">
          <summary className="text-xs font-medium text-muted-foreground select-none">Environment Variables</summary>
          <div className="mt-2 space-y-1 max-h-48 overflow-y-auto">
            {image.config.env_vars.map((ev) => (
              <div key={ev.name} className="rounded-sm bg-secondary/50 p-1.5 text-[10px] space-y-0.5">
                <code className="block font-mono text-foreground">{ev.name}</code>
                {ev.desc && <p className="text-muted-foreground">{ev.desc}</p>}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
