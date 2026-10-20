import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/api/client";
import { cardPngBlob, drawCard } from "@/lib/matrix-image";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";

const TITLE = "Styx sign-in card";
const EXPIRED = "Your session expired — sign in again.";
type Issued = { cells: Record<string, string>; confirm: string };
type Ask = "generate" | "remove" | null;

const is401 = (e: unknown) => e instanceof ApiError && e.status === 401;

export function MatrixCard() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["matrix-status"], queryFn: api.matrixStatus, retry: false });
  const [ask, setAsk] = useState<Ask>(null);
  const [password, setPassword] = useState("");
  const [issued, setIssued] = useState<Issued | null>(null);
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (issued && canvasRef.current) drawCard(canvasRef.current, issued.cells, TITLE);
  }, [issued]);

  const fail = (e: unknown, wrongPw: boolean) =>
    setError(is401(e) ? (wrongPw ? "Incorrect password." : EXPIRED)
      : e instanceof Error ? e.message : "Something went wrong.");

  const closeAsk = () => { setAsk(null); setPassword(""); setError(null); };

  async function submitPassword() {
    setBusy(true); setError(null);
    try {
      if (ask === "generate") {
        const r = await api.matrixGenerate(password);
        setIssued({ cells: r.cells, confirm: r.confirm_cell });
        setAnswer("");
      } else {
        await api.matrixRemove(password);
        await qc.invalidateQueries({ queryKey: ["matrix-status"] });
      }
      closeAsk();
    } catch (e) { fail(e, true); } finally { setBusy(false); }
  }

  async function activate() {
    setBusy(true); setError(null);
    try {
      await api.matrixActivate(answer);
      setIssued(null);
      await qc.invalidateQueries({ queryKey: ["matrix-status"] });
    } catch (e) {
      setError(is401(e) ? EXPIRED : "That value does not match. Check the card and try again.");
    } finally { setBusy(false); }
  }

  async function download() {
    if (!issued) return;
    const url = URL.createObjectURL(await cardPngBlob(issued.cells, TITLE));
    const a = document.createElement("a");
    a.href = url; a.download = "styx-sign-in-card.png"; a.click();
    URL.revokeObjectURL(url);
  }

  const enabled = status.data?.enabled === true;
  const expired = status.isError && is401(status.error);

  return (
    <Card className="styx-card">
      <CardHeader className="pb-4">
        <CardTitle>Sign-in card</CardTitle>
        <CardDescription>A printed card of codes, asked for after your password.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {expired && <p role="alert" className="text-sm text-destructive">{EXPIRED}</p>}
        {status.isError && !expired && (
          <p role="alert" className="text-sm text-destructive">Could not load card status.</p>
        )}

        {issued && (
          <div className="space-y-3">
            <p className="text-sm font-medium text-destructive">
              This card is shown once. Save or print it now.
            </p>
            <div className="matrix-print">
              <canvas ref={canvasRef} className="max-w-full rounded border border-border bg-white" />
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={download}>Download PNG</Button>
              <Button variant="outline" onClick={() => window.print()}>Print</Button>
            </div>
            <div className="space-y-2">
              <Label htmlFor="matrix-answer">Cell value</Label>
              <p className="text-sm text-muted-foreground">Enter cell {issued.confirm} to activate</p>
              <Input id="matrix-answer" value={answer} onChange={(e) => setAnswer(e.target.value)}
                autoComplete="off" />
              <Button onClick={activate} disabled={busy || !answer.trim()}>Activate</Button>
            </div>
          </div>
        )}

        {!issued && status.data && (
          <div className="flex items-center gap-3">
            {enabled && <span className="text-sm font-medium text-green-600">Active</span>}
            <Button onClick={() => setAsk("generate")}>{enabled ? "Regenerate" : "Generate card"}</Button>
            {enabled && (
              <Button variant="ghost" className="text-destructive" onClick={() => setAsk("remove")}>
                Remove
              </Button>
            )}
          </div>
        )}

        {ask && (
          <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); void submitPassword(); }}>
            <Label htmlFor="matrix-pw">Password</Label>
            <PasswordInput id="matrix-pw" value={password} autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)} />
            <div className="flex gap-2">
              <Button type="submit" disabled={busy || !password}>Continue</Button>
              <Button type="button" variant="ghost" onClick={closeAsk}>Cancel</Button>
            </div>
          </form>
        )}

        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}
