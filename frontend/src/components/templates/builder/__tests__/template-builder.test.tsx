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
