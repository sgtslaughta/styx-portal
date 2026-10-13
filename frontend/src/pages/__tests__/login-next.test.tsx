import { render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, test, expect, vi, beforeEach, afterEach } from "vitest";

const { a, auth } = vi.hoisted(() => ({
  a: { oauthProviders: vi.fn(), refreshSession: vi.fn() },
  auth: { user: null as null | { id: string }, loading: false, setupRequired: false,
    refresh: vi.fn(), logout: vi.fn() },
}));
vi.mock("@/api/client", () => ({ api: a }));
vi.mock("@/hooks/use-auth", () => ({ useAuth: () => auth }));
vi.mock("@/components/auth/LoginBrandPanel", () => ({ LoginBrandPanel: () => null }));
vi.mock("sonner", () => ({ toast: vi.fn() }));

import { LoginPage } from "../LoginPage";

const replace = vi.fn();
const realLocation = window.location;

function at(search: string) {
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { ...realLocation, origin: "http://localhost", search, replace, href: "" },
  });
  render(<MemoryRouter><LoginPage /></MemoryRouter>);
}

beforeEach(() => {
  vi.clearAllMocks();
  a.oauthProviders.mockResolvedValue([]);
  a.refreshSession.mockResolvedValue({ ok: true });
  auth.user = { id: "u1" };
  auth.loading = false;
});
afterEach(() => {
  Object.defineProperty(window, "location", { configurable: true, value: realLocation });
});

describe("LoginPage next-follow", () => {
  test("authenticated user is sent to a safe next at once", async () => {
    at("?next=%2Fsonarr%2F");
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/sonarr/"));
    expect(a.refreshSession).toHaveBeenCalledTimes(1);
  });

  test.each(["?next=%2F%2Fevil.com", "?next=%2F%5Cevil.com", "?next=https%3A%2F%2Fevil.com", ""])(
    "unsafe or missing next %s is ignored", async (q) => {
      at(q);
      await new Promise((r) => setTimeout(r, 0));
      expect(replace).not.toHaveBeenCalled();
      expect(a.refreshSession).not.toHaveBeenCalled();
    });

  test("anonymous user stays on the form", async () => {
    auth.user = null;
    at("?next=%2Fsonarr%2F");
    await new Promise((r) => setTimeout(r, 0));
    expect(replace).not.toHaveBeenCalled();
  });

  test("failed refresh keeps the user on the login page", async () => {
    a.refreshSession.mockRejectedValue(new Error("401"));
    at("?next=%2Fsonarr%2F");
    await waitFor(() => expect(a.refreshSession).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 0));
    expect(replace).not.toHaveBeenCalled();
  });
});
