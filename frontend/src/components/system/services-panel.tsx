import { useCallback, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Boxes, Globe, Plus } from "lucide-react";
import { api, type DiscoveredContainer, type MountJob, type Group, type ProxiedService, type ProxiedServiceInput, type ServicePreset } from "@/api/client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Drawer, DrawerContent, DrawerDescription, DrawerHeader, DrawerTitle } from "@/components/ui/drawer";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { ServiceForm } from "./service-form";
import { ServiceMount } from "./service-mount";
import { ServiceRow } from "./service-row";
import { serverFieldErrors, type FieldErrors } from "./service-validation";

type Editing = { kind: "new" } | { kind: "edit"; svc: ProxiedService } | { kind: "discovered"; c: DiscoveredContainer } | null;
const errMsg = (e: unknown, fb: string) => (e instanceof Error && e.message ? e.message : fb);

export function ServicesPanel() {
  const qc = useQueryClient();
  const [services, setServices] = useState<ProxiedService[] | null>(null);
  const [presets, setPresets] = useState<ServicePreset[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [picker, setPicker] = useState<DiscoveredContainer[] | null>(null);
  const [pickerBusy, setPickerBusy] = useState(false);
  const [editing, setEditing] = useState<Editing>(null);
  const [toDelete, setToDelete] = useState<ProxiedService | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, p, g] = await Promise.all([api.listServices(), api.listServicePresets(), api.listGroups()]);
      setServices(s); setPresets(p); setGroups(g); setError(null);
    } catch (e) { setError(errMsg(e, "Failed to load services")); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const openPicker = async () => {
    setPickerBusy(true);
    try { setPicker(await api.discoverContainers()); }
    catch (e) { toast.error(errMsg(e, "Discovery failed")); }
    finally { setPickerBusy(false); }
  };

  const submit = async (data: ProxiedServiceInput): Promise<FieldErrors | void> => {
    try {
      if (editing?.kind === "edit") { const { slug: _s, ...rest } = data; await api.updateService(editing.svc.id, rest); }
      else await api.createService(data);
    } catch (e) {
      const { fields, rest } = serverFieldErrors(e);
      if (rest.length || Object.keys(fields).length === 0) toast.error(rest.join("; ") || "Save failed");
      return fields;
    }
    toast.success("Service saved");
    setEditing(null);
    await load();
  };

  const toggle = async (s: ProxiedService, v: boolean) => {
    setBusyId(s.id);
    try { await api.setServiceEnabled(s.id, v); }
    catch (e) { toast.error(errMsg(e, "Failed to update service")); }
    finally { setBusyId(null); await load(); }
  };
  const remove = async () => {
    if (!toDelete) return;
    try { await api.deleteService(toDelete.id); toast.success("Service deleted"); }
    catch (e) { toast.error(errMsg(e, "Failed to delete service")); }
    await load();
  };

  return (
    <TooltipProvider>
      <Card className="styx-card">
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex min-w-0 flex-1 basis-64 items-center gap-3">
              <div className="shrink-0 rounded-lg bg-primary/10 p-2"><Globe className="h-5 w-5 text-primary" /></div>
              <div className="min-w-0">
                <CardTitle>Proxied services</CardTitle>
                <CardDescription>Each service is public on this hostname, behind the Styx login unless you say otherwise.</CardDescription>
              </div>
            </div>
            <div className="grid w-full grid-cols-1 gap-2 sm:flex sm:w-auto">
              <Button variant="outline" size="sm" disabled={pickerBusy} aria-busy={pickerBusy} onClick={() => void openPicker()}>
                <Boxes className="h-4 w-4" /> {pickerBusy ? "Looking..." : "Add from container"}
              </Button>
              <Button size="sm" onClick={() => setEditing({ kind: "new" })}><Plus className="h-4 w-4" /> Add service</Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {error ? (
            <div role="alert" className="flex items-center justify-between rounded-md border border-destructive/20 bg-destructive/5 p-3">
              <p className="text-sm text-destructive">{error}</p>
              <Button size="sm" variant="secondary" onClick={() => void load()}>Retry</Button>
            </div>
          ) : services === null ? (
            <p className="text-sm text-muted-foreground">Loading services...</p>
          ) : services.length === 0 ? (
            <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border px-4 py-10 text-center">
              <Globe className="h-8 w-8 text-muted-foreground/50" />
              <div className="max-w-sm space-y-1">
                <p className="text-sm font-medium">No services yet</p>
                <p className="text-sm text-muted-foreground">
                  Start from a preset (Jellyfin, Sonarr, Nextcloud and more) or expose a running container.
                </p>
              </div>
              <div className="flex flex-wrap justify-center gap-2">
                <Button size="sm" onClick={() => setEditing({ kind: "new" })}>Browse presets</Button>
                <Button size="sm" variant="outline" disabled={pickerBusy} onClick={() => void openPicker()}>Pick a container</Button>
              </div>
            </div>
          ) : (
            <ul className="space-y-2">
              {services.map((s) => (
                <ServiceRow key={s.id} s={s} busy={busyId === s.id}
                  lastMount={qc.getQueryData<MountJob | null>(["mount-job", s.id])?.state} onToggle={(v) => void toggle(s, v)}
                  onEdit={() => setEditing({ kind: "edit", svc: s })} onDelete={() => setToDelete(s)} />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Dialog open={picker !== null} onOpenChange={(o) => { if (!o) setPicker(null); }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Running containers</DialogTitle>
            <DialogDescription>Pick a container on this host to expose. Styx's own containers are hidden.</DialogDescription>
          </DialogHeader>
          <ul className="max-h-80 divide-y divide-border overflow-y-auto text-sm">
            {(picker ?? []).map((c) => (
              <li key={c.name} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <div className="truncate font-medium" title={c.name}>{c.name}</div>
                  <div className="truncate text-xs text-muted-foreground" title={c.image}>
                    <span className="font-mono">{c.image}</span>
                    <span className="ml-2 font-sans">{c.ports.length ? `${c.ports.length > 1 ? "Ports" : "Port"} ${c.ports.join(", ")}` : "No published ports"}</span>
                  </div>
                </div>
                <Button size="sm" variant="outline" disabled={c.ports.length === 0} aria-label={`Expose ${c.name}`}
                  onClick={() => { setPicker(null); setEditing({ kind: "discovered", c }); }}>Expose</Button>
              </li>
            ))}
            {picker?.length === 0 && (
              <li className="py-6 text-center text-muted-foreground">
                No eligible containers are running. Start one, or add it by URL with Add service.
              </li>
            )}
          </ul>
        </DialogContent>
      </Dialog>

      <Drawer open={editing !== null} onOpenChange={(o) => { if (!o) setEditing(null); }}>
        <DrawerContent className="w-full sm:w-[620px] sm:max-w-[620px]">
          <DrawerHeader>
            <DrawerTitle>{editing?.kind === "edit" ? `Edit ${editing.svc.name}` : "Add service"}</DrawerTitle>
            <DrawerDescription>Services are published on this hostname. Review each warning before saving.</DrawerDescription>
          </DrawerHeader>
          {editing && (
            <ServiceForm
              key={editing.kind === "edit" ? `${editing.svc.id}:${editing.svc.updated_at}:${editing.svc.mount_mode}` : editing.kind === "discovered" ? editing.c.name : "new"}
              initial={editing.kind === "edit" ? editing.svc : undefined}
              discovered={editing.kind === "discovered"
                ? { name: editing.c.name, port: editing.c.ports[0], preset: editing.c.suggested_preset } : null}
              presets={presets} groups={groups} loadContainers={api.discoverContainers}
              lead={editing.kind === "edit" ? <ServiceMount service={editing.svc}
                onChanged={(svc) => { setEditing({ kind: "edit", svc }); void load(); }} /> : undefined}
              onSubmit={submit} onCancel={() => setEditing(null)} />
          )}
        </DrawerContent>
      </Drawer>

      <ConfirmDialog open={toDelete !== null} onOpenChange={(o) => { if (!o) setToDelete(null); }}
        title={`Delete ${toDelete?.name ?? ""}?`} variant="destructive" confirmLabel="Delete"
        description="The route is removed immediately and the service stops being reachable." onConfirm={() => void remove()} />
    </TooltipProvider>
  );
}
