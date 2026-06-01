import { useState } from "react";
import { useNavigate } from "react-router";
import { api } from "@/api/client";
import { useAuth } from "@/hooks/use-auth";

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
    <div className="grid h-screen place-items-center">
      <form onSubmit={submit} className="w-80 space-y-3">
        <h1 className="text-xl font-semibold">Sign in</h1>
        <input className="w-full rounded border p-2" placeholder="Username"
               value={username} onChange={(e) => setU(e.target.value)} />
        <input className="w-full rounded border p-2" type="password" placeholder="Password"
               value={password} onChange={(e) => setP(e.target.value)} />
        {err && <p className="text-sm text-red-500">{err}</p>}
        <button className="w-full rounded bg-blue-600 p-2 text-white">Sign in</button>
      </form>
    </div>
  );
}
