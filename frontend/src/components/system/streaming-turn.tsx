import { useState, type ReactNode } from "react";
import type { Setting, SettingValue } from "@/api/client";
import { Seg } from "@/components/settings/seg";
import { CheckSetupDialog } from "./check-setup-dialog";
import { ReplaceTokenDialog } from "./replace-token-dialog";
import { TurnUsageMeter } from "./turn-usage-meter";

const PROVIDERS = [["cloudflare", "Cloudflare"], ["generic", "Own server"], ["none", "None"]] as const;
const CF_FIELDS = ["CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_TURN_TOKEN_ID", "CLOUDFLARE_ANALYTICS_TOKEN"];
const OWN_FIELDS = ["TURN_HOST", "TURN_PORT", "TURN_PROTOCOL", "TURN_TLS", "TURN_SHARED_SECRET", "TURN_USERNAME", "TURN_PASSWORD"];
const TOKEN = "CLOUDFLARE_TURN_API_TOKEN";

type Props = {
  provider: string;
  byKey: Record<string, Setting>;
  edits: Record<string, SettingValue>;
  disabled: boolean;
  onProvider: (v: string) => void;
  onToken: (v: string) => void;
  field: (key: string) => ReactNode;
};

function statusOf(provider: string, byKey: Record<string, Setting>, edits: Props["edits"]): { dot: string; text: string } {
  if (provider === "none") return { dot: "", text: "No relay. Viewers behind strict networks may fail to connect over WebRTC." };
  if (provider === "cloudflare") {
    const tokenOk = byKey[TOKEN]?.is_set || !!edits[TOKEN];
    return tokenOk ? { dot: "ok", text: "Cloudflare credentials saved. Run a check to verify them." }
      : { dot: "bad", text: "The Cloudflare API token is not set." };
  }
  return byKey.TURN_HOST?.value || edits.TURN_HOST ? { dot: "ok", text: "Own TURN server configured. Run a check to verify it." }
    : { dot: "bad", text: "The TURN host is not set." };
}

export function StreamingTurn({ provider, byKey, edits, disabled, onProvider, onToken, field }: Props) {
  const [token, setToken] = useState(false);
  const [check, setCheck] = useState(false);
  const st = statusOf(provider, byKey, edits);
  return (
    <fieldset className="grp">
      <legend>Relay for remote viewers (TURN)</legend>
      <div className="row wide">
        <span>Provider</span>
        <Seg label="TURN provider" value={provider as "none"} options={PROVIDERS} disabled={disabled} onChange={onProvider} />
      </div>
      {provider === "cloudflare" && CF_FIELDS.filter((k) => byKey[k]).map(field)}
      {provider === "cloudflare" && byKey[TOKEN] && (
        <div className={`row wide${edits[TOKEN] ? " changed" : ""}`}>
          <span>API token<small className="link-reset" style={{ opacity: 1, textDecoration: "none" }}>{edits[TOKEN] ? "Will be replaced on save" : byKey[TOKEN].is_set ? "Set" : "Not set"}</small></span>
          <button type="button" className="linkbtn" disabled={disabled} onClick={() => setToken(true)}>Replace token</button>
          <span />
        </div>
      )}
      {provider === "generic" && OWN_FIELDS.filter((k) => byKey[k]).map(field)}
      <div className="status-line">
        <span className={`sdot ${st.dot}`} /><span>{st.text}</span>
        {provider !== "none" && <button type="button" className="btn-ghost sm" onClick={() => setCheck(true)}>Check setup</button>}
      </div>
      {provider !== "none" && <TurnUsageMeter />}
      <ReplaceTokenDialog open={token} onOpenChange={setToken} onStage={onToken} />
      <CheckSetupDialog open={check} onOpenChange={setCheck} provider={provider} />
    </fieldset>
  );
}
