import { render, screen } from "@testing-library/react";
import { describe, test, expect, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TemplateBuilderModal } from "../template-builder-modal";

vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({ user: { id: "u1", role: "admin" } }),
}));

vi.mock("@/hooks/use-templates", () => ({
  useCreateTemplate: () => ({
    mutateAsync: vi.fn().mockResolvedValue({}),
    isPending: false,
  }),
  useUpdateTemplate: () => ({
    mutateAsync: vi.fn().mockResolvedValue({}),
    isPending: false,
  }),
}));

vi.mock("@/hooks/use-launch-config", () => ({
  useLaunchConfig: () => ({
    name: "test-template",
    image: "test-image",
    setName: vi.fn(),
    buildTemplateData: () => ({
      name: "test-template",
      image: "test-image",
      display_name: "Test Template",
      description: "",
      icon: "",
      category: "",
      config: {},
    }),
  }),
}));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("TemplateBuilderModal", () => {
  test("renders nothing when closed", () => {
    const { container } = wrap(
      <TemplateBuilderModal open={false} mode="new" onClose={() => {}} />
    );
    expect(container.querySelector("[role=dialog]")).not.toBeInTheDocument();
  });

  test("open in new mode shows title and buttons", () => {
    wrap(<TemplateBuilderModal open mode="new" onClose={() => {}} />);
    expect(screen.getByText("New template")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^save$/i })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /save & share/i })
    ).toBeInTheDocument();
  });

  test("open in edit mode shows correct title", () => {
    wrap(
      <TemplateBuilderModal
        open
        mode="edit"
        template={{ id: "t1", display_name: "Original" } as any}
        onClose={() => {}}
      />
    );
    expect(screen.getByText("Edit template")).toBeInTheDocument();
  });

  test("open in clone mode shows correct title", () => {
    wrap(
      <TemplateBuilderModal
        open
        mode="clone"
        template={{ id: "t1", display_name: "Original" } as any}
        onClose={() => {}}
      />
    );
    expect(screen.getByText("Clone template")).toBeInTheDocument();
  });
});
