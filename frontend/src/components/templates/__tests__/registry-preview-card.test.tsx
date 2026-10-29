import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { RegistryPreviewCard } from "../registry-preview-card";
import type { RegistryImage } from "@/lib/types";

const img: RegistryImage = {
  name: "sonarr",
  description: "Full description of Sonarr",
  project_logo: "https://x/logo.png",
  category: "Media",
  stars: 10,
  monthly_pulls: 5000,
  version: "4.0.1",
  stable: true,
  tags: [{ tag: "latest", desc: "Stable releases" }],
  config: { application_setup: "<b>bold</b> setup", env_vars: [], volumes: [], ports: [] },
  architectures: [{ arch: "amd64", tag: "amd64-latest" }],
  changelog: [{ date: "2026-01-01", desc: "Did a thing" }],
  github_url: "https://github.com/x/y",
  project_url: "https://example.com",
};

describe("RegistryPreviewCard", () => {
  it("shows info without iframe or injected HTML", () => {
    const { container } = render(<RegistryPreviewCard image={img} />);
    expect(screen.getByText("Full description of Sonarr")).toBeTruthy();
    expect(screen.getByText(/4\.0\.1/)).toBeTruthy();
    expect(container.querySelector("iframe")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toContain("<b>bold</b> setup");
  });
});
