import { render, screen, fireEvent } from "@testing-library/react";
import { describe, test, expect } from "vitest";
import { TemplateBuilder } from "../template-builder";
import { useLaunchConfig } from "@/hooks/use-launch-config";

function Harness({ isAdmin }: { isAdmin: boolean }) {
  const cfg = useLaunchConfig({});
  return <TemplateBuilder cfg={cfg} isAdmin={isAdmin} />;
}

describe("TemplateBuilder", () => {
  test("renders section rail and switches to Resources panel", () => {
    render(<Harness isAdmin />);
    fireEvent.click(screen.getByRole("button", { name: /resources/i }));
    expect(screen.getByText(/memory limit/i)).toBeInTheDocument();
  });

  test("non-admin sees Security section controls locked", () => {
    render(<Harness isAdmin={false} />);
    fireEvent.click(screen.getByRole("button", { name: /security/i }));
    expect(screen.getAllByText(/requires admin/i).length).toBeGreaterThan(0);
  });

  test("admin Security section is not locked", () => {
    render(<Harness isAdmin />);
    fireEvent.click(screen.getByRole("button", { name: /security/i }));
    expect(screen.queryByText(/requires admin/i)).toBeNull();
  });
});

describe("TemplateBuilder on Kubernetes", () => {
  function K8s() {
    const cfg = useLaunchConfig({});
    return <TemplateBuilder cfg={cfg} isAdmin k8s />;
  }

  test("hides Security section and Docker-only fields", () => {
    render(<K8s />);
    expect(screen.queryByRole("button", { name: /security/i })).toBeNull();
    expect(screen.getByText(/docker-only settings are hidden/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /resources/i }));
    expect(screen.queryByText(/restart policy/i)).toBeNull();
    expect(screen.getByText(/memory limit/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /raw docker/i }));
    expect(screen.queryByText(/extra docker args/i)).toBeNull();
    expect(screen.getByText(/entrypoint/i)).toBeInTheDocument();
  });

  test("shows them on Docker", () => {
    render(<Harness isAdmin />);
    expect(screen.getByRole("button", { name: /security/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /resources/i }));
    expect(screen.getByText(/restart policy/i)).toBeInTheDocument();
  });
});
