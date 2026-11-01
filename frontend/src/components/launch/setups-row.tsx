import { SectionHead } from "@/components/common/section-head";
import { Glyph } from "./glyph";
import type { ServiceTemplate } from "@/lib/types";

export function SetupsRow({ setups, onPick }: { setups: ServiceTemplate[]; onPick: (t: ServiceTemplate) => void }) {
  return (
        <section>
          <SectionHead title="Your setups" note="one click, saved settings" />
          <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-2.5">
            {setups.map((s) => (
              <button key={s.id} type="button" onClick={() => onPick(s)} className="relative flex items-center gap-2.5 rounded-[10px] border border-border bg-card px-3 py-2.5 text-left hover:border-muted-foreground">
                <Glyph name={s.display_name} icon={s.icon} size={34} />
                <span className="min-w-0"><strong className="block truncate text-sm font-semibold">{s.display_name}</strong><small className="block truncate text-[12.5px] text-muted-foreground" title={s.image}>{s.image.split("/").pop()}</small></span>
                <span className="ml-auto text-[13px] font-semibold text-[var(--gold-text)]">Launch</span>
              </button>
            ))}
          </div>
        </section>
  );
}
