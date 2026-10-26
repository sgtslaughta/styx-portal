interface Props {
  showProfile: boolean;
  showGpu: boolean;
  useProfile: boolean;
  onProfile: (v: boolean) => void;
  useGpu: boolean;
  onGpu: (v: boolean) => void;
}

export function LaunchOptions({ showProfile, showGpu, useProfile, onProfile, useGpu, onGpu }: Props) {
  if (!showProfile && !showGpu) return null;
  return (
    <div className="space-y-2 text-sm">
      {showProfile && (
        <label className="flex items-center gap-2">
          <input type="checkbox" className="h-4 w-4 accent-primary" checked={useProfile}
                 onChange={(e) => onProfile(e.target.checked)} />
          Use my persistent profile
        </label>
      )}
      {showGpu && (
        <label className="flex items-center gap-2">
          <input type="checkbox" className="h-4 w-4 accent-primary" checked={useGpu}
                 onChange={(e) => onGpu(e.target.checked)} />
          Use GPU
        </label>
      )}
    </div>
  );
}
