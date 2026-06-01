import { useState } from "react";
import { useNavigate } from "react-router";
import zxcvbn from "zxcvbn";
import { api } from "@/api/client";
import { useAuth } from "@/hooks/use-auth";

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
    <div className="grid h-screen place-items-center">
      <form onSubmit={submit} className="w-80 space-y-3">
        <h1 className="text-xl font-semibold">Create admin account</h1>
        <input className="w-full rounded border p-2" placeholder="Username"
               value={username} onChange={(e) => setU(e.target.value)} />
        <input className="w-full rounded border p-2" type="password" placeholder="Password"
               value={password} onChange={(e) => setP(e.target.value)} />
        <div className="h-1 rounded bg-gray-200">
          <div className="h-1 rounded bg-green-500" style={{ width: `${(score + 1) * 20}%` }} />
        </div>
        {err && <p className="text-sm text-red-500">{err}</p>}
        <button className="w-full rounded bg-blue-600 p-2 text-white" disabled={score < 3}>
          Create admin
        </button>
      </form>
    </div>
  );
}
