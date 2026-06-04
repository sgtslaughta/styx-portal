import { useState } from "react";
import { useNavigate } from "react-router";
import zxcvbn from "zxcvbn";
import { api } from "@/api/client";
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LoginBrandPanel } from "@/components/auth/LoginBrandPanel";

const STRENGTH_LABELS = ["Very weak", "Weak", "Fair", "Good", "Strong"];
const STRENGTH_COLORS = ["bg-destructive", "bg-warning", "bg-warning", "bg-success", "bg-success"];

export function SetupWizard() {
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [err, setErr] = useState("");
  const nav = useNavigate();
  const { refresh } = useAuth();
  const score = password ? zxcvbn(password).score : 0;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (score < 3) { setErr("Password too weak"); return; }
    try {
      await api.setup({ username, password });
      await refresh();
      nav("/");
    } catch (e) { setErr((e as Error).message); }
  }

  return (
    <div className="grid min-h-screen md:grid-cols-2">
      <LoginBrandPanel />
      <div className="flex items-center justify-center bg-muted px-6 py-12">
        <div className="w-full max-w-sm space-y-6">
          <div className="space-y-1 text-center">
            <h1 className="text-2xl font-bold">Create admin account</h1>
            <p className="text-sm text-muted-foreground">Set up your Styx Portal administrator account.</p>
          </div>

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
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setP(e.target.value)}
                required
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
            <Button type="submit" className="w-full" disabled={score < 3}>
              Create admin
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
