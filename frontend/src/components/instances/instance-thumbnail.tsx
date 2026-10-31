import { api } from "@/api/client";
import { Thumbnail } from "@/components/common/thumbnail";

interface InstanceThumbnailProps {
  instanceId: string;
  icon: string | null;
  isLive: boolean;
  fill?: boolean;
}

/** Detail-pane preview for a Docker instance: 30s refresh plus a manual re-capture button. */
export function InstanceThumbnail({ instanceId, icon, isLive, fill }: InstanceThumbnailProps) {
  return (
    <Thumbnail
      src={api.screenshotUrl(instanceId)}
      icon={icon}
      isLive={isLive}
      fill={fill}
      refreshMs={30000}
      onRefresh={() => api.refreshScreenshot(instanceId)}
    />
  );
}
