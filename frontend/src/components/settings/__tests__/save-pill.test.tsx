import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import { SavePill } from "../save-pill";

describe("SavePill", () => {
  test("hidden at 0", () => {
    render(<SavePill count={0} onSave={vi.fn()} onDiscard={vi.fn()} />);
    expect(screen.queryByTestId("save-pill")).toBeNull();
  });
  test("singular/plural and actions", () => {
    const onSave = vi.fn();
    const { rerender } = render(<SavePill count={1} onSave={onSave} onDiscard={vi.fn()} />);
    expect(screen.getByText(/unsaved change$/)).toBeTruthy();
    rerender(<SavePill count={3} onSave={onSave} onDiscard={vi.fn()} />);
    expect(screen.getByText(/unsaved changes$/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(onSave).toHaveBeenCalled();
  });
});
