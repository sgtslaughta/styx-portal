import { render, screen } from "@testing-library/react";
import { describe, test, expect } from "vitest";
import { AgentUpdateChip } from "../agent-update-chip";

describe("AgentUpdateChip", () => {
  test.each([
    ["requested", "Update queued"],
    ["updating", "Updating…"],
    ["ok", "Updated"],
    ["rolled_back", "Rolled back"],
    ["failed", "Update failed"],
  ])("%s -> %s", (state, label) => {
    render(<AgentUpdateChip state={state} />);
    expect(screen.getByText(label)).toBeTruthy();
  });

  test("error shown in title", () => {
    render(<AgentUpdateChip state="rolled_back" error="gate timeout" />);
    expect(screen.getByText("Rolled back").getAttribute("title")).toBe("gate timeout");
  });

  test("empty state renders nothing", () => {
    const { container } = render(<AgentUpdateChip state="" />);
    expect(container.firstChild).toBeNull();
  });
});
