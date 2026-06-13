import { render, screen } from "@testing-library/react";
import { describe, test, expect } from "vitest";
import { LockedField } from "../locked-field";

describe("LockedField", () => {
  test("non-admin: child disabled + lock note shown", () => {
    render(
      <LockedField locked label="Privileged">
        <input data-testid="ctl" />
      </LockedField>
    );
    expect(screen.getByTestId("ctl")).toBeDisabled();
    expect(screen.getByText(/requires admin/i)).toBeInTheDocument();
  });

  test("admin: child enabled", () => {
    render(
      <LockedField locked={false} label="Privileged">
        <input data-testid="ctl" />
      </LockedField>
    );
    expect(screen.getByTestId("ctl")).not.toBeDisabled();
  });
});
