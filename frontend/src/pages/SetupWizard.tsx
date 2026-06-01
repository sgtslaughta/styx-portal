import { useState } from "react";
import { useNavigate } from "react-router";
import zxcvbn from "zxcvbn";
import { Shield } from "lucide-react";
import { api } from "@/api/client";
import { useAuth } from "@/hooks/use-auth";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

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
    <div className="grid h-screen place-items-center bg-background px-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="gap-1 pb-4">
          <div className="flex items-center gap-2">
            <Shield className="h-5 w-5 text-primary" />
            <CardTitle>Create admin account</CardTitle>
          </div>
          <CardDescription>Set up your Selkies Hub administrator account</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="username" className="block text-sm font-medium">Username</label>
              <Input
                id="username"
                placeholder="admin-username"
                value={username}
                onChange={(e) => setU(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="password" className="block text-sm font-medium">Password</label>
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
        </CardContent>
      </Card>
    </div>
  );
}
