import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SectionHead } from "../section-head";

describe("SectionHead", () => {
  it("renders heading, rule, note, action in order", () => {
    const { container } = render(<SectionHead title="Desktops" note="3 machines" action={<button>New</button>} />);
    const h = screen.getByRole("heading", { name: "Desktops", level: 2 });
    const rule = container.querySelector(".gold-rule")!;
    expect(rule).toHaveAttribute("aria-hidden", "true");
    const note = screen.getByText("3 machines");
    const btn = screen.getByRole("button", { name: "New" });
    const after = (a: Node, b: Node) => a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING;
    expect(after(h, rule)).toBeTruthy();
    expect(after(rule, note)).toBeTruthy();
    expect(after(note, btn)).toBeTruthy();
  });
});
