import { useState } from "react";
import { toast } from "sonner";
import { api, type ProxiedService } from "@/api/client";
import { Button } from "@/components/ui/button";
import { IconSettings } from "@/components/system/icon-settings";
import { Section } from "./service-form-parts";

/** Drawer section: pick an emoji / image / auto badge, or re-fetch the app's own favicon. */
type Staged = { kind: "auto" | "emoji" | "image"; value?: string } | null;

export function ServiceIconSection({ service, onChanged, onStage }: {
  service: ProxiedService; onChanged: (s: ProxiedService) => void; onStage: (c: Staged) => void;
}) {
  const [busy, setBusy] = useState(false);
  const useOwn = async () => {
    setBusy(true);
    try {
      const svc = await api.refreshServiceIcon(service.id);
      toast.success(`Now using ${service.name}'s own icon.`);
      onChanged(svc);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Section title="Icon" hint="Styx fetches the app's own icon once. A different choice is saved with the service.">
      <IconSettings
        id={service.id}
        kind={service.icon_kind}
        iconUrl={`/api/services/${service.id}/icon?v=${service.icon_etag}`}
        onStage={onStage}
        extra={
          <Button size="sm" variant="secondary" onClick={() => void useOwn()} disabled={busy} aria-busy={busy}>
            {`Use ${service.name}'s own icon`}
          </Button>
        }
      />
    </Section>
  );
}
