import { useState } from "react";
import { useNavigate, Navigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import zxcvbn from "zxcvbn";
import { api } from "@/api/client";
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { Loader2 } from "lucide-react";
import { LoginBrandPanel } from "@/components/auth/LoginBrandPanel";

const STRENGTH_LABELS = ["Very weak", "Weak", "Fair", "Good", "Strong"];
const STRENGTH_COLORS = ["bg-destructive", "bg-warning", "bg-warning", "bg-success", "bg-success"];

function PreRow({ ok, label, detail, warnOnly }: { ok: boolean; label: string; detail: string; warnOnly?: boolean }) {
  const color = ok ? "text-success" : warnOnly ? "text-warning" : "text-destructive";
  return (
    <div className="flex items-center justify-between">
      <span>{label}</span>
      <span className={color}>{ok ? "✓" : warnOnly ? "!" : "✗"} {detail}</span>
    </div>
  );
}

export function SetupWizard() {
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [err, setErr] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const nav = useNavigate();
  const { refresh, setupRequired, loading } = useAuth();
  const score = password ? zxcvbn(password).score : 0;
  const { data: pre } = useQuery({ queryKey: ["setup-preflight"], queryFn: api.setupPreflight, retry: false });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (score < 3) { setErr("Password too weak"); return; }
    setSubmitting(true);
    try {
      await api.setup({ username, password });
      await refresh();
      nav("/");
    } catch (e) { setErr((e as Error).message); }
    finally { setSubmitting(false); }
  }

  // Setup is a one-time flow: once an admin exists, never show it again.
  if (!loading && !setupRequired) return <Navigate to="/login" replace />;

  return (
    <div className="grid min-h-screen md:grid-cols-2">
      <LoginBrandPanel />
      <div className="styx-auth-form flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm space-y-6">
          <div className="space-y-1 text-center">
            <h1 className="text-2xl font-bold">Create admin account</h1>
            <p className="text-sm text-muted-foreground">Set up your Styx Portal administrator account.</p>
          </div>

          {pre && (
            <div className="space-y-1 rounded-md border border-border p-3 text-xs">
              <p className="font-medium">Environment check</p>
              <PreRow ok={pre.docker.ok} label="Docker" detail={pre.docker.detail} />
              <PreRow ok={pre.data_writable} label="Data volume" detail={pre.data_writable ? "writable" : "not writable"} />
              <PreRow ok={pre.domain_set} label="Domain" detail={pre.domain_set ? "configured" : "DOMAIN not set — using localhost"} warnOnly />
              <p className="text-muted-foreground">Ingress mode: {pre.deploy_mode}</p>
            </div>
          )}

          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="username" className="block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Username
              </label>
              <Input
                id="username"
                placeholder="admin-username"
                value={username}
                onChange={(e) => setU(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="password" className="block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Password
              </label>
              <PasswordInput
                id="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setP(e.target.value)}
                required
                aria-invalid={err ? true : undefined}
              />
              {password && (
                <div className="space-y-2 pt-2">
                  <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                    <div
                      className={`h-full transition-all ${STRENGTH_COLORS[score]}`}
                      style={{ width: `${(score + 1) * 20}%` }}
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Strength:</span>
                    <span className={`text-xs font-medium ${
                      score < 2 ? "text-destructive" : score < 3 ? "text-warning" : "text-success"
                    }`}>
                      {STRENGTH_LABELS[score]}
                    </span>
                  </div>
                </div>
              )}
            </div>
            {err && (
              <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
                {err}
              </div>
            )}
            <Button type="submit" className="w-full" disabled={score < 3 || submitting}>
              {submitting ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Creating…</> : "Create admin"}
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
