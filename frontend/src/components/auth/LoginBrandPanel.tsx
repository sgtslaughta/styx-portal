import { Waves } from "lucide-react";

import { RippleCanvas } from "./RippleCanvas";

/**
 * Theme-aware animated brand panel for the login split layout.
 * Responds to .dark class: dark theme = rich navy gradient + bright ripple,
 * light theme = ethereal sky gradient + subtle ripple.
 */
export function LoginBrandPanel() {
  return (
    <div className="styx-brand hidden md:flex flex-col justify-between p-10">
      <RippleCanvas />
      <div className="flex items-center gap-2">
        <Waves className="h-6 w-6" style={{ color: "rgb(var(--brand-ripple-r), var(--brand-ripple-g), var(--brand-ripple-b))" }} />
        <span className="text-lg font-extrabold tracking-wider">STYX PORTAL</span>
      </div>
      <div>
        <h2 className="text-3xl font-bold leading-tight">
          Cross over to your
          <br />
          workspaces.
        </h2>
        <p className="mt-3 max-w-xs text-sm" style={{ color: "var(--brand-fg-muted)" }}>
          Secure remote desktops, on demand.
        </p>
      </div>
    </div>
  );
}
