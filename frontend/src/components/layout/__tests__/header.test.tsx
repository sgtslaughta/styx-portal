import { readFileSync } from "node:fs";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Header as RawHeader } from "../header";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { ComponentProps } from "react";

const Header = (p: ComponentProps<typeof RawHeader>) => <TooltipProvider><RawHeader {...p} /></TooltipProvider>;

const auth = vi.hoisted(() => ({ role: "admin" }));
vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({ user: { username: "alice", role: auth.role }, logout: vi.fn() }),
}));
vi.mock("@/components/layout/opening-menu", () => ({ OpeningMenu: () => null }));
vi.mock("@/theme/ThemeProvider", () => ({ useTheme: () => ({ theme: "dark", setTheme: vi.fn() }) }));

describe("Header", () => {
  beforeEach(() => { auth.role = "admin"; });

  it("keeps user controls right-aligned", () => {
    const src = readFileSync("src/components/layout/header.tsx", "utf8");
    expect(src).toContain("ml-auto flex items-center gap-2");
  });

  it("hides the Admin tab from non-admins", () => {
    auth.role = "user";
    render(<Header activeTab="home" onTabChange={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Admin" })).toBeNull();
  });

  it("calls onTabChange('admin') and marks the active tab", async () => {
    const onTabChange = vi.fn();
    render(<Header activeTab="home" onTabChange={onTabChange} />);
    expect(screen.getByRole("button", { name: "Home" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Home" })).toHaveClass("gold-underline");
    await userEvent.click(screen.getByRole("button", { name: "Admin" }));
    expect(onTabChange).toHaveBeenCalledWith("admin");
  });

  it("renders no running/paused count chips", () => {
    render(<Header activeTab="home" onTabChange={vi.fn()} />);
    expect(screen.queryByText(/running|paused/)).toBeNull();
  });
});
