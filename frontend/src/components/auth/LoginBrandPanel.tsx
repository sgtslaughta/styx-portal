import { Waves } from "lucide-react";

/**
 * Always-dark animated brand panel for the login split layout.
 * Visual only — no props, no logic. Theme-independent by design.
 */
export function LoginBrandPanel() {
  return (
    <div className="styx-brand hidden md:flex flex-col justify-between p-10">
      <div className="flex items-center gap-2">
        <Waves className="h-6 w-6 text-sky-400" />
        <span className="text-lg font-extrabold tracking-wider">STYX PORTAL</span>
      </div>
      <div>
        <h2 className="text-3xl font-bold leading-tight">
          Cross over to your
          <br />
          workspaces.
        </h2>
        <p className="mt-3 max-w-xs text-sm text-white/60">
          Secure remote desktops, on demand.
        </p>
      </div>
    </div>
  );
}
