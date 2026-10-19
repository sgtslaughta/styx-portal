import { toast } from "sonner";
import { useOpenChoice } from "@/components/open-prompt";
import { openPending } from "@/lib/connect-wipe";
import { writeRecent } from "@/lib/workspace";
import type { Instance } from "@/lib/types";

/** Open a running instance per the Workspaces preference; remembered as the most recent workspace. */
export function useInstanceConnect() {
  const choose = useOpenChoice();
  return (instance: Instance) => {
    writeRecent({ kind: "instance", id: instance.id });
    choose("workspaces", instance.name, (mode) => {
      openPending(mode, `Launching ${instance.name}…`, async () => `/i/${instance.subdomain}/`)
        .catch((e: Error) => toast.error(`Connect failed: ${e.message}`));
    });
  };
}
