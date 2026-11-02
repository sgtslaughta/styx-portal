import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { Glyph } from "./glyph";
import { SetupsRow } from "./setups-row";
import { SectionHead } from "@/components/common/section-head";
import { useRegistryImages } from "@/hooks/use-registry";
import { Button } from "@/components/ui/button";
import { isLinuxserverImage } from "./resolve-template";
import { rankCats, splitCats } from "./catalog-cats";

const TOP_CATS = 9;
import type { RegistryImage, ServiceTemplate } from "@/lib/types";

interface Props {
  setups: ServiceTemplate[];
  searchRef: React.Ref<HTMLInputElement>;
  onPickImage: (img: RegistryImage) => void;
  isAdmin: boolean;
  onLaunchSetup: (t: ServiceTemplate) => void;
  onPickSetup: (t: ServiceTemplate) => void;
  onEditSetup: (t: ServiceTemplate) => void;
  onCustom: (image: string) => void;
}

export function CatalogGrid({ setups, searchRef, isAdmin, onPickImage, onLaunchSetup, onPickSetup, onEditSetup, onCustom }: Props) {
  const { data: images = [], isLoading } = useRegistryImages();
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("All");
  const [custom, setCustom] = useState("");
  const [allCats, setAllCats] = useState(false);
  const ranked = useMemo(() => rankCats(images.map((i) => i.category)), [images]);
  // Top tags only; the selected tag stays visible even when it's outside the top set.
  const shown = allCats ? ranked : [...new Set([...ranked.slice(0, TOP_CATS), ...(cat !== "All" ? [cat] : [])])];
  const term = q.trim().toLowerCase();
  const list = images.filter((i) => (cat === "All" || splitCats(i.category).includes(cat))
    && (!term || i.name.toLowerCase().includes(term) || (i.category ?? "").toLowerCase().includes(term)));
  const showSetups = !term && cat === "All" && setups.length > 0;
  const saved = (i: RegistryImage) => setups.some((s) => isLinuxserverImage(s.image, i.name));

  return (
    <div className="space-y-5">
      <label className="sticky -top-4 z-10 flex items-center gap-2.5 rounded-[10px] shadow-[0_8px_8px_-6px_var(--background)] md:static md:shadow-none border border-border bg-card px-3.5 py-2.5 text-muted-foreground focus-within:ring-2 focus-within:ring-ring">
        <Search className="size-4" aria-hidden />
        <input ref={searchRef} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search LinuxServer images" aria-label="Search LinuxServer images" className="flex-1 bg-transparent text-foreground outline-none" />
      </label>
      <div className="flex flex-wrap gap-1.5">
        {["All", ...shown].map((c) => (
          <button key={c} type="button" aria-pressed={c === cat} onClick={() => setCat(c)}
            className="rounded-full border border-border px-3 py-1 text-[13.5px] max-sm:min-h-9 text-muted-foreground aria-pressed:border-foreground aria-pressed:bg-foreground aria-pressed:text-background">{c}</button>
        ))}
        {ranked.length > TOP_CATS && (
          <button type="button" onClick={() => setAllCats((v) => !v)} aria-expanded={allCats}
            className="rounded-full px-3 py-1 text-[13.5px] text-primary hover:underline">{allCats ? "Fewer" : `${ranked.length - TOP_CATS} more`}</button>
        )}
      </div>
      {showSetups && <SetupsRow setups={setups} isAdmin={isAdmin} onLaunch={onLaunchSetup} onCustomise={onPickSetup} onEdit={onEditSetup} />}
      <section>
        <SectionHead title="LinuxServer catalog" note={isLoading ? "loading" : `${list.length} images`} />
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-[repeat(auto-fill,minmax(210px,1fr))] sm:gap-3">
          {list.map((i) => (
            <button key={i.name} type="button" onClick={() => onPickImage(i)} className="grid grid-cols-[minmax(0,1fr)] content-start gap-2.5 min-w-0 rounded-xl border border-transparent bg-card p-3 text-left sm:p-3.5 hover:border-border hover:bg-muted">
              <span className="flex items-center gap-3"><Glyph name={i.name} icon={i.project_logo} size={38} /><span className="min-w-0"><strong className="block truncate font-semibold">{i.name}</strong><span className="block truncate text-[12.5px] text-muted-foreground">{splitCats(i.category).join(", ")}</span></span></span>
              <p className="line-clamp-2 text-[13.5px] text-muted-foreground">{i.description}</p>
              {saved(i) && <span className="text-xs text-[var(--gold-text)]">You have a saved setup</span>}
            </button>
          ))}
        </div>
        <form className="mt-[18px] flex flex-col items-stretch gap-2.5 sm:flex-row sm:items-center rounded-xl border border-dashed border-border p-3.5 text-sm text-muted-foreground" onSubmit={(e) => { e.preventDefault(); if (custom.trim()) onCustom(custom.trim()); }}>
          <label htmlFor="nc-other">Use another image</label>
          <input id="nc-other" value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="registry/image:tag" className="min-w-0 flex-1 rounded-lg border border-border bg-card px-3 py-2 text-foreground max-sm:min-h-10 max-sm:w-full" />
          <Button type="submit" variant="secondary" disabled={!custom.trim()}>Continue</Button>
        </form>
      </section>
    </div>
  );
}
