import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, test, expect, vi, beforeEach } from "vitest";

const { a, auth } = vi.hoisted(() => ({
  a: { oauthProviders: vi.fn(), refreshSession: vi.fn(), setupPreflight: vi.fn() },
  auth: { user: null as null | { id: string }, loading: false, setupRequired: false,
    refresh: vi.fn(), logout: vi.fn() },
}));
vi.mock("@/api/client", () => ({ api: a, withRetry: (fn: () => unknown) => fn() }));
vi.mock("@/hooks/use-auth", () => ({ useAuth: () => auth }));
vi.mock("@/components/auth/LoginBrandPanel", () => ({ LoginBrandPanel: () => null }));
vi.mock("sonner", () => ({ toast: vi.fn() }));

import { LoginPage } from "../LoginPage";
import { SetupWizard } from "../SetupWizard";

function at(path: string) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/" element={<div>HOME</div>} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/setup" element={<SetupWizard />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  a.oauthProviders.mockResolvedValue([]);
  a.setupPreflight.mockResolvedValue(undefined);
  auth.user = null; auth.loading = false; auth.setupRequired = false;
});

describe("signed-in landing", () => {
  test("signed-in user on /setup (after creating admin) lands on /", () => {
    auth.user = { id: "u1" };
    at("/setup");
    expect(screen.getByText("HOME")).toBeTruthy();
  });
  test("anonymous user on /setup with admin existing goes to /login", () => {
    at("/setup");
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeTruthy();
  });
  test("signed-in user on /login without next goes to /", () => {
    auth.user = { id: "u1" };
    at("/login");
    expect(screen.getByText("HOME")).toBeTruthy();
  });
});
