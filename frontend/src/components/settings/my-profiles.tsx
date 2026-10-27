import { UserRound } from "lucide-react";
import { api } from "@/api/client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ProfilesList } from "@/components/system/profiles-list";

export function MyProfiles() {
  return (
    <Card className="styx-card">
      <CardHeader className="pb-4">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-primary/10 p-2">
            <UserRound className="h-5 w-5 text-primary" />
          </div>
          <div>
            <CardTitle>My profiles</CardTitle>
            <CardDescription>Persistent profiles saved per template. Reset to start fresh.</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <ProfilesList load={api.getMyProfiles} remove={api.deleteMyProfile} actionLabel="Reset" />
      </CardContent>
    </Card>
  );
}
