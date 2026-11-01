import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { expect, test } from "vitest";
import { AdminActiveContext, useAdminPoll } from "../use-admin-poll";

const wrap = (active: boolean) => ({ children }: { children: ReactNode }) => (
  <AdminActiveContext.Provider value={active}>{children}</AdminActiveContext.Provider>
);

test("polls while the admin tab is visible", () => {
  expect(renderHook(() => useAdminPoll(30000), { wrapper: wrap(true) }).result.current).toBe(30000);
  expect(renderHook(() => useAdminPoll(30000)).result.current).toBe(30000);
});

test("stops polling while the admin tab is hidden", () => {
  expect(renderHook(() => useAdminPoll(30000), { wrapper: wrap(false) }).result.current).toBe(false);
});
