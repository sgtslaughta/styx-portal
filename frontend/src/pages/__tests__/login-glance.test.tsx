import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, test, expect, vi } from "vitest";

vi.mock("@/api/client", () => ({ api: { oauthProviders: vi.fn().mockResolvedValue([]) }, withRetry: (fn: () => unknown) => fn() }));
vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({ user: null, loading: false, setupRequired: false, refresh: vi.fn(), logout: vi.fn() }),
}));
vi.mock("sonner", () => ({ toast: vi.fn() }));

import { LoginPage } from "../LoginPage";

function setup() {
  render(<MemoryRouter><LoginPage /></MemoryRouter>);
}

describe("LoginPage Glance layout", () => {
  test("no subtitle copy", () => {
    setup();
    expect(screen.queryByText(/Secure remote desktops/)).toBeNull();
  });
  test("headline has the reveal class", () => {
    setup();
    const h = screen.getByRole("heading", { name: "Cross over to your workspaces." });
    expect(h.parentElement?.classList.contains("reveal")).toBe(true);
  });
  test("logo sits inside the form panel", () => {
    setup();
    expect(screen.getByTestId("login-form-panel")).toContainElement(screen.getByTestId("login-logo"));
    expect(screen.getByTestId("login-logo")).toHaveTextContent("STYX PORTAL");
  });
  test("Sign in is a glass button", () => {
    setup();
    expect(screen.getByRole("button", { name: "Sign in" }).classList.contains("glass")).toBe(true);
  });
});
