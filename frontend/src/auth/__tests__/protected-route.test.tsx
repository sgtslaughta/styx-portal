import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router";
import { describe, test, expect, vi } from "vitest";

const { auth } = vi.hoisted(() => ({
  auth: { user: null as null | Record<string, unknown>, loading: false, setupRequired: false },
}));
vi.mock("@/hooks/use-auth", () => ({ useAuth: () => auth }));

import { ProtectedRoute } from "../ProtectedRoute";

function at() {
  render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/change-password" element={<div>CHANGE</div>} />
        <Route path="/" element={<ProtectedRoute><div>APP</div></ProtectedRoute>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProtectedRoute must_change_pw", () => {
  test("forced password change redirects and never renders the app", () => {
    auth.user = { id: "1", role: "member", must_change_pw: true };
    at();
    expect(screen.getByText("CHANGE")).toBeTruthy();
    expect(screen.queryByText("APP")).toBeNull();
  });
  test("normal user sees the app", () => {
    auth.user = { id: "1", role: "member", must_change_pw: false };
    at();
    expect(screen.getByText("APP")).toBeTruthy();
  });
});
