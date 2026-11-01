import { render, screen, fireEvent } from "@testing-library/react";
import { describe, test, expect, vi } from "vitest";
import { SettingField } from "../setting-field";
import type { Setting } from "@/api/client";

const presets = [
  { id: "light", label: "Light", cpus: 2, memory_gb: 2, gpu: false },
  { id: "standard", label: "Standard", cpus: 4, memory_gb: 4, gpu: false },
  { id: "heavy", label: "Heavy", cpus: 6, memory_gb: 8, gpu: true },
];
const setting = { key: "CONTAINER_SIZE_PRESETS", label: "Container size presets", help: "", type: "json", value: presets, default: presets, min: null, max: null } as unknown as Setting;

describe("size presets editor", () => {
  test("adding a 4th preset stages the JSON list", () => {
    const onChange = vi.fn();
    render(<SettingField setting={setting} value={undefined} disabled={false} onChange={onChange} onRestore={vi.fn()} onResetDefault={vi.fn()} onClear={vi.fn()} />);
    fireEvent.click(screen.getByText("Edit 3 sizes"));
    fireEvent.click(screen.getByText("Add a size"));
    fireEvent.click(screen.getByText("Done"));
    const staged = onChange.mock.calls[0]![0] as { id: string }[];
    expect(staged).toHaveLength(4);
    expect(new Set(staged.map((p) => p.id)).size).toBe(4);
  });

  test("cannot exceed six or remove the last", () => {
    render(<SettingField setting={setting} value={undefined} disabled={false} onChange={vi.fn()} onRestore={vi.fn()} onResetDefault={vi.fn()} onClear={vi.fn()} />);
    fireEvent.click(screen.getByText("Edit 3 sizes"));
    for (let i = 0; i < 3; i++) fireEvent.click(screen.getByText("Add a size"));
    expect((screen.getByText("Add a size") as HTMLButtonElement).disabled).toBe(true);
  });

  test("removing a preset stages a shorter list, last one cannot be removed", () => {
    const onChange = vi.fn();
    render(<SettingField setting={setting} value={undefined} disabled={false} onChange={onChange} onRestore={vi.fn()} onResetDefault={vi.fn()} onClear={vi.fn()} />);
    fireEvent.click(screen.getByText("Edit 3 sizes"));
    fireEvent.click(screen.getByLabelText("Remove size 1"));
    fireEvent.click(screen.getByLabelText("Remove size 1"));
    expect((screen.getByLabelText("Remove size 1") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByText("Done"));
    expect((onChange.mock.calls[0]![0] as { id: string }[]).map((p) => p.id)).toEqual(["heavy"]);
  });
});
