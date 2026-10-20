import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, test, expect, vi, beforeEach } from "vitest";

const { a, auth, nav } = vi.hoisted(() => ({
  a: { oauthProviders: vi.fn(), refreshSession: vi.fn(), login: vi.fn(), loginMatrix: vi.fn() },
  auth: { user: null, loading: false, setupRequired: false, refresh: vi.fn(), logout: vi.fn() },
  nav: vi.fn(),
}));
vi.mock("@/api/client", () => ({ api: a, withRetry: (fn: () => unknown) => fn() }));
vi.mock("@/hooks/use-auth", () => ({ useAuth: () => auth }));
vi.mock("@/components/auth/LoginBrandPanel", () => ({ LoginBrandPanel: () => null }));
vi.mock("sonner", () => ({ toast: vi.fn() }));
vi.mock("react-router", async (orig) => ({ ...(await orig<object>()), useNavigate: () => nav }));

import { LoginPage } from "../LoginPage";

async function toMatrixStep() {
  render(<MemoryRouter><LoginPage /></MemoryRouter>);
  await userEvent.type(screen.getByLabelText(/email or username/i), "bob");
  await userEvent.type(screen.getByLabelText(/^password/i), "pw");
  await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
}

beforeEach(() => {
  vi.clearAllMocks();
  a.oauthProviders.mockResolvedValue([]);
  a.login.mockResolvedValue({ mfa_required: true, challenge: ["B4", "E7", "A2"] });
});

describe("LoginPage matrix step", () => {
  test("shows three cell inputs when mfa_required", async () => {
    await toMatrixStep();
    for (const c of ["B4", "E7", "A2"]) expect(await screen.findByLabelText(c)).toBeTruthy();
    expect(screen.queryByLabelText(/^password/i)).toBeNull();
  });

  test("submits answers and navigates on success", async () => {
    a.loginMatrix.mockResolvedValue({ id: "u", username: "bob", role: "user", must_change_pw: false });
    await toMatrixStep();
    await userEvent.type(await screen.findByLabelText("B4"), "abc");
    await userEvent.type(screen.getByLabelText("E7"), "def");
    await userEvent.type(screen.getByLabelText("A2"), "ghj");
    await userEvent.click(screen.getByRole("button", { name: /verify|sign in/i }));
    await waitFor(() => expect(a.loginMatrix).toHaveBeenCalledWith(["ABC", "DEF", "GHJ"]));
    await waitFor(() => expect(nav).toHaveBeenCalledWith("/"));
  });

  test("shows error and keeps cells on failure", async () => {
    a.loginMatrix.mockRejectedValue(new Error("Invalid code"));
    await toMatrixStep();
    await userEvent.type(await screen.findByLabelText("B4"), "abc");
    await userEvent.type(screen.getByLabelText("E7"), "def");
    await userEvent.type(screen.getByLabelText("A2"), "ghj");
    await userEvent.click(screen.getByRole("button", { name: /verify|sign in/i }));
    expect((await screen.findByRole("alert")).textContent).toContain("Wrong code — check the cells and try again.");
    expect((screen.getByLabelText("B4") as HTMLInputElement).value).toBe("");
    expect(screen.getByLabelText("E7")).toBeTruthy();
  });

  test("expired sign-in returns to password step", async () => {
    a.loginMatrix.mockRejectedValue(new Error("Sign-in expired"));
    await toMatrixStep();
    for (const c of ["B4", "E7", "A2"]) await userEvent.type(await screen.findByLabelText(c), "abc");
    await userEvent.click(screen.getByRole("button", { name: /verify|sign in/i }));
    expect((await screen.findByRole("alert")).textContent).toContain("Sign-in expired — enter your password again.");
    expect(screen.getByLabelText(/^password/i)).toBeTruthy();
  });

  test("Back returns to password step", async () => {
    await toMatrixStep();
    await userEvent.click(await screen.findByRole("button", { name: /back/i }));
    expect(screen.getByLabelText(/^password/i)).toBeTruthy();
  });
});
