import { render } from "@testing-library/react";
import { describe, test, expect, vi } from "vitest";
import { WorkspaceRow } from "../workspace-row";

const base = { icon: <i />, name: "Box", line: "x", dot: { dotClass: "bg-success", label: "Online" }, onSelect: vi.fn() };

describe("WorkspaceRow", () => {
  test("row without quick action reserves a same-size trailing slot", () => {
    const { container } = render(<ul><WorkspaceRow {...base} /></ul>);
    const slot = container.querySelector("[data-slot='quick']")!;
    expect(slot.getAttribute("aria-hidden")).toBe("true");
    const withQuick = render(<ul><WorkspaceRow {...base} quick={{ label: "Connect", onClick: vi.fn() }} /></ul>);
    const btn = withQuick.getByRole("button", { name: "Connect" });
    expect(slot.className).toContain("size-9");
    expect(btn.className).toContain("size-9");
  });
});
