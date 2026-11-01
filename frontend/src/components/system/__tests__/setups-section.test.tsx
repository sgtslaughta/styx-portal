import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, test, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthContext, type AuthUser } from "@/auth/AuthContext";
import { SetupsSection } from "../setups-section";

const m = vi.hoisted(() => ({ listTemplates: vi.fn(), deleteTemplate: vi.fn() }));
vi.mock("@/api/client", () => ({ api: m }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
let modal: Record<string, unknown> | null = null;
vi.mock("@/components/templates/template-builder-modal", () => ({
  TemplateBuilderModal: (p: Record<string, unknown>) => { modal = p; return <div>builder</div>; },
}));

const sh = { id: "s1", name: "chrome", display_name: "Chrome", image: "lscr.io/linuxserver/chromium", cpu_limit: "4", memory_limit: "4g", shared: true, owner_id: "a" };
const mine = { id: "p1", name: "mine", display_name: "Mine", image: "x/y", shared: false, owner_id: "u1" };

function wrap(ui: React.ReactElement, role = "admin") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const auth = { user: { id: "u1", username: "u", email: "u@x", role } as AuthUser, loading: false, setupRequired: false, refresh: vi.fn(), logout: vi.fn() };
  return render(<QueryClientProvider client={qc}><AuthContext.Provider value={auth}>{ui}</AuthContext.Provider></QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks(); modal = null;
  m.listTemplates.mockImplementation(async (shared?: boolean) => (shared ? [sh] : [sh, mine]));
  m.deleteTemplate.mockResolvedValue(undefined);
});

describe("SetupsSection", () => {
  test("lists shared setups and own private templates", async () => {
    wrap(<SetupsSection />);
    await screen.findByText("Chrome");
    expect(screen.getByText(/4 CPU · 4g/)).toBeTruthy();
    expect(await screen.findByText("Mine")).toBeTruthy();
  });
  test("New setup opens the builder shared-only", async () => {
    wrap(<SetupsSection />);
    fireEvent.click(await screen.findByRole("button", { name: /New setup/ }));
    expect(modal).toMatchObject({ mode: "new", sharedOnly: true });
  });
  test("Edit opens the builder with the template", async () => {
    wrap(<SetupsSection />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Chrome" }));
    expect(modal).toMatchObject({ mode: "edit", template: sh });
  });
  test("Delete asks to confirm then deletes", async () => {
    wrap(<SetupsSection />);
    fireEvent.click(await screen.findByRole("button", { name: "Delete Chrome" }));
    expect(m.deleteTemplate).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
    await waitFor(() => expect(m.deleteTemplate).toHaveBeenCalledWith("s1"));
  });
  test("only=mine shows just private templates, nothing when none", async () => {
    wrap(<SetupsSection only="mine" />, "member");
    await screen.findByText("Mine");
    expect(screen.queryByText("Chrome")).toBeNull();
  });
});
