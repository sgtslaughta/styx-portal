import { useState } from "react";
import { useNavigate } from "react-router";
import { LogIn } from "lucide-react";
import { api } from "@/api/client";
import { useAuth } from "@/hooks/use-auth";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function LoginPage() {
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [err, setErr] = useState("");
  const nav = useNavigate();
  const { refresh } = useAuth();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      await api.login({ username, password });
      await refresh();
      nav("/");
    } catch (e) { setErr((e as Error).message); }
  }

  return (
    <div className="grid h-screen place-items-center bg-background px-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="gap-1 pb-4">
          <div className="flex items-center gap-2">
            <LogIn className="h-5 w-5 text-primary" />
            <CardTitle>Sign in to Selkies Hub</CardTitle>
          </div>
          <CardDescription>Enter your credentials to access the dashboard</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="username" className="block text-sm font-medium">Username</label>
              <Input
                id="username"
                placeholder="your-username"
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
        </CardContent>
      </Card>
    </div>
  );
}
