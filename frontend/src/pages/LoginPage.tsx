import { useEffect, useRef, useState } from "react";
import { useNavigate, Navigate } from "react-router";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { LoginBrandPanel } from "@/components/auth/LoginBrandPanel";
import { friendlyLoginError } from "@/lib/auth-errors";
import { safeNext } from "@/lib/safe-next";
import { KeyRound, Loader2, Waves } from "lucide-react";

export function LoginPage() {
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [err, setErr] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [providers, setProviders] = useState<{ name: string; display_label: string; icon_url: string | null }[]>([]);
  const nav = useNavigate();
  const { refresh, setupRequired, loading, user } = useAuth();

  // SameSite=Strict: a cross-site link to /sonarr/ lands here with
  // ?next=/sonarr/ even when the session is valid. Already signed in → mint a
  // fresh styx_proxy (refresh) and follow next at once (full navigation:
  // /sonarr/, /w/, /i/ are Traefik routes, not SPA). Refresh failing = stay.
  const loggingIn = useRef(false); // submit() handles next/must_change_pw itself
  useEffect(() => {
    if (loading || !user || loggingIn.current) return;
    const target = safeNext(new URLSearchParams(window.location.search).get("next"));
    if (!target) return;
    api.refreshSession()
      .then(() => window.location.replace(target))
      .catch(() => {});
  }, [loading, user]);

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

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("expired")) {
      toast("Your session expired — please sign in again.");
      window.history.replaceState({}, "", "/login");
    }
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    setSubmitting(true);
    loggingIn.current = true;
    try {
      const result = await api.login({ username, password });
      if (result.must_change_pw) {
        await refresh();
        nav("/change-password");
        return;
      }
      await refresh();
      // Forward-auth redirects land here with ?next=/w/{sub}/ or /{slug}/ —
      // return the user there. safeNext allows same-site paths only.
      const target = safeNext(new URLSearchParams(window.location.search).get("next"));
      if (target) {
        window.location.href = target; // Traefik routes, not SPA
      } else {
        nav("/");
      }
    } catch (e) {
      loggingIn.current = false;
      setErr(friendlyLoginError((e as Error).message));
    } finally {
      setSubmitting(false);
    }
  }

  // No users yet → send the first visitor to the admin setup flow instead of a
  // login form they could never satisfy.
  if (!loading && setupRequired) return <Navigate to="/setup" replace />;
  // Signed in, nothing to follow: the form has no purpose.
  if (!loading && user && !loggingIn.current
      && !safeNext(new URLSearchParams(window.location.search).get("next"))) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="grid min-h-screen md:grid-cols-[3fr_2fr]">
      <LoginBrandPanel />
      <div className="styx-auth-form flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm space-y-6">
          <div className="flex items-center justify-center gap-2 md:hidden"><Waves className="h-5 w-5 text-primary" aria-hidden /><span className="text-base font-extrabold tracking-wider">STYX PORTAL</span></div>
          <div className="space-y-1 text-center">
            <h1 className="text-2xl font-semibold">Sign in</h1>
            <p className="text-sm text-muted-foreground">Welcome back.</p>
          </div>

          {providers.length > 0 && (
            <div className="space-y-2">
              {providers.map((p) => (
                <a
                  key={p.name}
                  href={api.oauthStartUrl(p.name)}
                  className="flex w-full items-center justify-center gap-2 rounded-md border border-border bg-background p-2.5 text-sm font-medium hover:bg-accent"
                >
                  {p.icon_url
                    ? <img src={p.icon_url} alt="" className="h-5 w-5 object-contain" />
                    : <KeyRound className="h-4 w-4 text-muted-foreground" />}
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
              <label htmlFor="username" className="block text-sm font-medium">
                Email or username
              </label>
              <Input
                id="username"
                placeholder="you@example.com"
                value={username}
                onChange={(e) => setU(e.target.value)}
                aria-invalid={err ? true : undefined}
                required
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="password" className="block text-sm font-medium">
                Password
              </label>
              <PasswordInput
                id="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setP(e.target.value)}
                aria-invalid={err ? true : undefined}
                aria-describedby={err ? "login-error" : undefined}
                required
              />
            </div>
            {err && (
              <div id="login-error" role="alert" className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
                <div>{err}</div>
                <button type="button" onClick={() => { setErr(""); window.history.replaceState({}, "", "/login"); }}
                        className="mt-1 text-xs underline underline-offset-2 hover:no-underline">
                  Dismiss
                </button>
              </div>
            )}
            <Button type="submit" className="w-full" size="default" disabled={submitting}>
              {submitting ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Signing in…</> : "Sign in"}
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
