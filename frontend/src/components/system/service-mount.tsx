import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Check, ChevronRight } from "lucide-react";
import { api, type MountJob, type ProxiedService } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Stepper } from "@/components/ui/stepper";
import { MountConsentDialog } from "./mount-consent-dialog";

export const ACTIVE = ["pending", "running"];
export const pollWhile = (state?: string) => (ACTIVE.includes(state ?? "") ? 1000 : false);

/** Backup detail is a long host path: show the timestamp folder, keep the full path as a tooltip. */
const shortSteps = (steps: MountJob["steps"]) => steps.map((s) =>
  s.id === "backup" && s.detail?.includes("/") ? { ...s, detail: s.detail.split("/").filter(Boolean).slice(-1)[0], title: s.detail } : s);

export function ServiceMount({ service, onChanged }: { service: ProxiedService; onChanged?: (svc: ProxiedService) => void }) {
  const { id, name, slug } = service;
  const qc = useQueryClient();
  const [asking, setAsking] = useState(false);
  const enabled = service.kind === "docker-local" && service.mount_mode === "path";

  const plan = useQuery({ queryKey: ["mount-plan", id], queryFn: () => api.mountPlan(id), enabled });
  const job = useQuery<MountJob | null>({
    queryKey: ["mount-job", id], enabled,
    queryFn: () => api.mountLatest(id).catch((e: { status?: number }) => (e?.status === 404 ? null : Promise.reject(e))),
    refetchInterval: (q) => pollWhile(q.state.data?.state),
  });
  const apply = useMutation({
    mutationFn: (consent: boolean) => api.mountApply(id, consent),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["mount-job", id] });
      void qc.invalidateQueries({ queryKey: ["mount-plan", id] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const focus = useMutation({
    mutationFn: () => {
      const { name: n, icon, kind, upstream_url, container, container_port, auth_mode, bypass_rules, allowed_groups,
        verify_tls, health_path, preset_id, enabled: en, pass_identity, frame_ok } = service;
      return api.updateService(id, { name: n, icon, kind, upstream_url, container, container_port, mount_mode: "cookie-root",
        auth_mode, bypass_rules, allowed_groups, verify_tls, health_path, preset_id, enabled: en, pass_identity, frame_ok });
    },
    onSuccess: (svc) => { toast.success(`${name} now opens in focus mode.`); onChanged?.(svc); },
    onError: (e: Error) => toast.error(e.message),
  });

  const jobState = job.data?.state;
  const outcomeRef = useRef<HTMLParagraphElement>(null);
  // The outcome paragraph only exists once plan and job have both loaded; Radix's open autofocus
  // runs before that, so focus on the next frame, after it.
  const ready = !!plan.data && !job.isLoading;
  useEffect(() => {
    if (!ready || (jobState !== "rolled_back" && jobState !== "failed")) return;
    const id = requestAnimationFrame(() => outcomeRef.current?.focus());
    return () => cancelAnimationFrame(id);
  }, [jobState, ready]);
  const seen = useRef<string | null>(null);
  const jobKey = job.data ? `${job.data.id}:${job.data.state}` : null;
  useEffect(() => {
    if (jobKey === seen.current) return;
    seen.current = jobKey;
    if (jobState && !ACTIVE.includes(jobState)) void qc.invalidateQueries({ queryKey: ["mount-plan", id] });
  }, [jobKey, jobState, qc, id]);

  if (!enabled) return null;
  if (plan.isError) return (
    <p className="text-sm text-muted-foreground">Couldn't check {name}'s settings. {(plan.error as Error).message}</p>
  );
  if (!plan.data || job.isLoading) return null;
  const p = plan.data;
  const j = job.data ?? null;
  const running = j !== null && ACTIVE.includes(j.state);
  const start = () => (p.needs_consent ? setAsking(true) : apply.mutate(false));
  const retry = <Button size="sm" onClick={start} disabled={apply.isPending}>Try again</Button>;

  const setBtn = <Button size="sm" onClick={start} disabled={apply.isPending}>{`Set base path to /${slug}`}</Button>;
  const verified = (
    <p className="flex items-center gap-2 text-sm"><Check className="h-4 w-4 rounded-full ring-2 ring-success text-success-foreground" />Base path is set to /{slug}</p>
  );

  let body: React.ReactNode;
  if (running) body = <Stepper steps={shortSteps(j.steps)} />;
  else if (j?.state === "rolled_back") body = (
    <>
      <Stepper steps={shortSteps(j.steps)} />
      <p ref={outcomeRef} role="alert" tabIndex={-1} className="text-sm text-destructive outline-none">Couldn't switch {name} to /{slug}, so Styx put its settings back.</p>
      {j.log_excerpt && (
        <details className="group text-sm"><summary className="inline-flex cursor-pointer list-none items-center gap-1 [&::-webkit-details-marker]:hidden"><ChevronRight className="size-4 transition-transform group-open:rotate-90 motion-reduce:transition-none" aria-hidden />App log</summary>
          <pre className="mt-1 max-h-48 overflow-auto rounded bg-muted p-2 text-xs">{j.log_excerpt}</pre>
        </details>
      )}
      <div className="flex flex-wrap gap-2">
        {retry}
        <Button size="sm" variant="outline" disabled={focus.isPending} onClick={() => focus.mutate()}>Use focus mode instead</Button>
      </div>
    </>
  );
  else if (j?.state === "failed") body = (
    <>
      <p ref={outcomeRef} role="alert" tabIndex={-1} className="text-sm text-destructive outline-none">The change failed and Styx couldn't put the old settings back. Your backup is in {j.backup_dir}.</p>
      {retry}
    </>
  );
  else if (p.method === null) body = (
    <p className="text-sm text-muted-foreground">{p.reason} You can set the base path to /{slug} in the app yourself, or use a preset.</p>
  );
  else if (p.changes.length > 0) body = (
    <>
      {j?.state === "done" && <Stepper steps={shortSteps(j.steps)} />}
      {setBtn}
    </>
  );
  else body = (
    <>
      {j?.state === "done" && <Stepper steps={shortSteps(j.steps)} />}
      {j?.state === "done"
        ? <p className="text-sm text-success-foreground">Base path set. {name} answers at /{slug}.</p>
        : verified}
    </>
  );
  return (
    <section aria-label="Base path" className="space-y-3">
      <h3 className="text-base font-semibold">Base path</h3>
      {body}
      <MountConsentDialog open={asking} appName={name} changes={p.changes} onCancel={() => setAsking(false)}
        onConfirm={() => { setAsking(false); apply.mutate(true); }} />
    </section>
  );
}
