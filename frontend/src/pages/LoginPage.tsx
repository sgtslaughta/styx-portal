import { useEffect, useState } from "react";
import { useNavigate, Navigate } from "react-router";
import { api } from "@/api/client";
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LoginBrandPanel } from "@/components/auth/LoginBrandPanel";

export function LoginPage() {
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [err, setErr] = useState("");
  const [providers, setProviders] = useState<{ name: string; display_label: string }[]>([]);
  const nav = useNavigate();
  const { refresh, setupRequired, loading } = useAuth();

  useEffect(() => {
    api.oauthProviders().then(setProviders).catch(() => {});
  }, []);

  useEffect(() => {
    const ssoError = new URLSearchParams(window.location.search).get("error");
    if (ssoError) {
      const errorMap: Record<string, string> = {
        not_authorized: "This account is not authorized. Ask an admin for an invite.",
        email_unverified: "Your identity provider did not confirm a verified email.",
        account_disabled: "This account is disabled.",
        state_mismatch: "Sign-in session expired. Please try again.",
        bad_state: "Sign-in session expired. Please try again.",
        missing_state: "Sign-in session expired. Please try again.",
        oauth_failed: "Single sign-on failed. Please try again.",
        unknown_provider: "Single sign-on failed. Please try again.",
      };
      setErr(errorMap[ssoError] || "An error occurred during sign-in. Please try again.");
    }
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      await api.login({ username, password });
      await refresh();
      nav("/");
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  // No users yet → send the first visitor to the admin setup flow instead of a
  // login form they could never satisfy.
  if (!loading && setupRequired) return <Navigate to="/setup" replace />;

  return (
    <div className="grid min-h-screen md:grid-cols-2">
      <LoginBrandPanel />
      <div className="styx-auth-form flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm space-y-6">
          <div className="space-y-1 text-center">
            <h1 className="text-2xl font-bold">Sign in</h1>
            <p className="text-sm text-muted-foreground">Welcome back. Please sign in to continue.</p>
          </div>

          {providers.length > 0 && (
            <div className="space-y-2">
              {providers.map((p) => (
                <a
                  key={p.name}
                  href={api.oauthStartUrl(p.name)}
                  className="flex w-full items-center justify-center rounded-md border border-border bg-background p-2.5 text-sm font-medium hover:bg-accent"
                >
                  Continue with {p.display_label}
                </a>
              ))}
              <div className="flex items-center gap-3 pt-1 text-xs text-muted-foreground">
                <span className="h-px flex-1 bg-border" />
                or
                <span className="h-px flex-1 bg-border" />
              </div>
            </div>
          )}

          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="username" className="block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Email or username
              </label>
              <Input
                id="username"
                placeholder="you@example.com"
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
            </div>
            {err && (
              <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
                {err}
              </div>
            )}
            <Button type="submit" className="w-full" size="default">
              Sign in
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
