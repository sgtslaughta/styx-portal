import { useEffect, useState } from "react";
import { Monitor } from "lucide-react";
import { api, type Workstation } from "@/api/client";
import { Button } from "@/components/ui/button";

export function WorkstationGrid() {
  const [rows, setRows] = useState<Workstation[]>([]);
  useEffect(() => {
    const load = () => api.myWorkstations().then(setRows).catch(() => {});
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);
  if (rows.length === 0) return null;

  const connect = async (ws: Workstation) => {
    const { url } = await api.workstationConnectUrl(ws.id);
    window.open(url, "_blank", "noopener");
  };

  return (
    <section className="space-y-2 mb-4">
      <h3 className="text-sm font-medium text-muted-foreground">Workstations</h3>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {rows.map((ws) => (
          <div key={ws.id}
               className="rounded-lg border border-border bg-surface p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Monitor className="h-6 w-6 text-muted-foreground" />
              <div>
                <p className="font-medium">{ws.name}</p>
                <p className="text-xs text-muted-foreground">
                  {ws.status === "online" ? "Online" : `Offline (${ws.status})`}
                  {" · "}{ws.display_server}
                </p>
              </div>
            </div>
            <Button
              size="sm"
              disabled={ws.status !== "online"}
              onClick={() => connect(ws)}
            >
              Connect
            </Button>
          </div>
        ))}
      </div>
    </section>
  );
}
