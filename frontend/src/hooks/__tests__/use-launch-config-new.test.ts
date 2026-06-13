import { renderHook, act } from "@testing-library/react";
import { describe, test, expect } from "vitest";
import { useLaunchConfig } from "../use-launch-config";

describe("useLaunchConfig new fields", () => {
  test("new fields default and serialize into buildTemplateData", () => {
    const { result } = renderHook(() => useLaunchConfig({}));
    act(() => result.current.setRestartPolicy("unless-stopped"));
    act(() =>
      result.current.setExtraPorts([
        {
          container_port: 8080,
          label: "code",
          slug: "code",
          strip_prefix: true,
        },
      ])
    );
    const data = result.current.buildTemplateData();
    expect(data.restart_policy).toBe("unless-stopped");
    expect(data.extra_ports[0].slug).toBe("code");
    expect(data.read_only_rootfs).toBe(false);
    expect(data.shared).toBe(false);
  });

  test("prefills new fields from a template (clone)", () => {
    const tmpl: any = {
      display_name: "G",
      image: "img",
      restart_policy: "always",
      devices: ["/dev/dri:/dev/dri"],
      extra_ports: [
        {
          container_port: 9000,
          label: "api",
          slug: "api",
          strip_prefix: false,
        },
      ],
      privileged: true,
    };
    const { result } = renderHook(() => useLaunchConfig({ template: tmpl }));
    expect(result.current.restartPolicy).toBe("always");
    expect(result.current.extraPorts[0].slug).toBe("api");
    expect(result.current.privileged).toBe(true);
  });
});
