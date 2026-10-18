import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

vi.mock("@/hooks/use-auth", () => ({ useAuth: () => ({ user: { role: "admin" }, loading: false }) }));
vi.mock("../nav-config", () => {
  const sec = (id: string) => ({ id, label: id, description: "", tooltip: "", icon: () => null, Component: () => <p>pane-{id}</p> });
  return { visibleCategories: () => [{ id: "c", label: "C", icon: () => null, sections: [sec("overview"), sec("services")] }] };
});

import { TooltipProvider } from "@/components/ui/tooltip";
import { SettingsLayout } from "../settings-layout";

const renderLayout = () => render(<TooltipProvider><SettingsLayout /></TooltipProvider>);

afterEach(() => window.history.replaceState(null, "", "/"));

describe("SettingsLayout", () => {
  test("opens the first section by default", () => {
    renderLayout();
    expect(screen.getByText("pane-overview")).toBeInTheDocument();
  });
  test("?setup= opens the services section", () => {
    window.history.replaceState(null, "", "/?setup=s1");
    renderLayout();
    expect(screen.getByText("pane-services")).toBeInTheDocument();
  });
});
