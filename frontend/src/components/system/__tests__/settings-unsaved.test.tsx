import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { describe, expect, test, vi } from "vitest";

const upd = vi.hoisted(() => vi.fn().mockResolvedValue({}));
vi.mock("@/api/client", () => ({
  api: {
    getSystemSettings: vi.fn().mockResolvedValue([
      { group: "g", label: "G", settings: [{ key: "S", label: "S", help: "", type: "secret", value: null, default: null, min: null, max: null, is_set: true }, { key: "A", label: "A", help: "", type: "str", value: "x", default: "x", min: null, max: null }] },
    ]),
    updateSystemSettings: upd, resetSystemSetting: vi.fn(),
  },
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { SystemSettingsPanel } from "../system-settings-panel";
import { UnsavedProvider, useUnsaved } from "@/components/settings/unsaved-context";

const Count = () => <output data-testid="n">{useUnsaved().count}</output>;

describe("SystemSettingsPanel unsaved count", () => {
  test("reports dirty count, resets on discard and unmount", async () => {
    const qc = new QueryClient();
    const ui = (show: boolean) => (
      <QueryClientProvider client={qc}><MemoryRouter><UnsavedProvider>
        <Count />{show && <SystemSettingsPanel />}
      </UnsavedProvider></MemoryRouter></QueryClientProvider>
    );
    const { rerender } = render(ui(true));
    fireEvent.change(await screen.findByLabelText("A"), { target: { value: "y" } });
    expect(screen.getByTestId("n").textContent).toBe("1");
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    expect(screen.getByTestId("n").textContent).toBe("0");
    fireEvent.change(screen.getByLabelText("A"), { target: { value: "z" } });
    expect(screen.getByTestId("n").textContent).toBe("1");
    rerender(ui(false));
    expect(screen.getByTestId("n").textContent).toBe("0");
  });

  test("secret Clear joins the batch with other edits", async () => {
    const qc = new QueryClient();
    render(<QueryClientProvider client={qc}><MemoryRouter><UnsavedProvider>
      <Count /><SystemSettingsPanel />
    </UnsavedProvider></MemoryRouter></QueryClientProvider>);
    fireEvent.change(await screen.findByLabelText("A"), { target: { value: "y" } });
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.getByTestId("n").textContent).toBe("2");
    expect(upd).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await vi.waitFor(() => expect(upd).toHaveBeenCalledWith({ S: "", A: "y" }));
  });
});
