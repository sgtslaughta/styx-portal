import { Pencil } from "lucide-react";
import { SectionHead } from "@/components/common/section-head";
import { Glyph } from "./glyph";
import type { ServiceTemplate } from "@/lib/types";

interface Props {
  setups: ServiceTemplate[];
  isAdmin: boolean;
  onLaunch: (t: ServiceTemplate) => void;
  onCustomise: (t: ServiceTemplate) => void;
  onEdit: (t: ServiceTemplate) => void;
}

export function SetupsRow({ setups, isAdmin, onLaunch, onCustomise, onEdit }: Props) {
  return (
    <section>
      <SectionHead title="Your setups" note="one click, saved settings" />
      <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-2.5">
        {setups.map((s) => (
          <div key={s.id} className="flex items-center gap-1 rounded-[10px] border border-border bg-card pr-2 hover:border-muted-foreground">
            <button type="button" aria-label={`Customise ${s.display_name}`} onClick={() => onCustomise(s)} className="flex min-w-0 flex-1 items-center gap-2.5 px-3 py-2.5 text-left">
              <Glyph name={s.display_name} icon={s.icon} size={34} />
              <span className="min-w-0"><strong className="block truncate text-sm font-semibold">{s.display_name}</strong><small className="block truncate text-[12.5px] text-muted-foreground" title={s.image}>{s.image.split("/").pop()}</small></span>
            </button>
            {isAdmin && (
              <button type="button" aria-label={`Edit ${s.display_name}`} onClick={() => onEdit(s)} className="rounded-md p-1.5 text-muted-foreground hover:text-foreground"><Pencil className="size-3.5" aria-hidden /></button>
            )}
            <button type="button" aria-label={`Launch ${s.display_name}`} onClick={() => onLaunch(s)} className="rounded-md px-1.5 py-1 text-[13px] font-semibold text-[var(--gold-text)] hover:underline">Launch</button>
          </div>
        ))}
      </div>
    </section>
  );
}
