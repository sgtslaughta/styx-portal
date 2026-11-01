import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import type { Setting, SettingValue } from "@/api/client";
import { SettingField } from "../setting-field";

const s = (o: Partial<Setting>): Setting => ({
  key: "BAN_DURATION", label: "IP ban duration (s)", help: "h", type: "int",
  value: 86400, default: 86400, min: 60, max: 604800, ...o,
});

function Harness({ setting }: { setting: Setting }) {
  const [v, setV] = useState<SettingValue | undefined>(undefined);
  return (
    <SettingField setting={setting} value={v} disabled={false} onChange={setV}
      onRestore={() => setV(undefined)} onResetDefault={vi.fn()} onClear={vi.fn()} />
  );
}

describe("SettingField", () => {
  test("shows converted unit, flags change, restores", () => {
    const { container } = render(<Harness setting={s({})} />);
    const input = screen.getByLabelText("IP ban duration") as HTMLInputElement;
    expect(input.value).toBe("24");
    expect(input.className).toMatch(/no-spin/);
    expect(screen.getByText("hours")).toBeTruthy();
    const row = container.querySelector(".row")!;
    expect(row.hasAttribute("data-changed")).toBe(false);
    fireEvent.change(input, { target: { value: "48" } });
    expect(row.getAttribute("data-changed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: /Restore/ }));
    expect(input.value).toBe("24");
    expect(row.hasAttribute("data-changed")).toBe(false);
  });
  test("rate edit keeps the period", () => {
    const onChange = vi.fn();
    render(<SettingField setting={s({ key: "RATE_LIMIT_AUTH", label: "Auth", type: "rate", value: "5/60", default: "5/60", min: null, max: null })}
      value={undefined} disabled={false} onChange={onChange} onRestore={vi.fn()} onResetDefault={vi.fn()} onClear={vi.fn()} />);
    expect(screen.getByText("per min")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Auth"), { target: { value: "9" } });
    expect(onChange).toHaveBeenCalledWith("9/60");
  });
});
