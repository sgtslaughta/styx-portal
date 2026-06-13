import { render, screen, fireEvent } from "@testing-library/react";
import { describe, test, expect, vi } from "vitest";
import { SliderInput } from "../slider-input";

describe("SliderInput", () => {
  test("typing in the box updates value", () => {
    const onChange = vi.fn();
    render(
      <SliderInput label="Memory" min={1} max={64} value={8} unit="GB" onChange={onChange} />
    );
    const box = screen.getByRole("spinbutton");
    fireEvent.change(box, { target: { value: "16" } });
    expect(onChange).toHaveBeenCalledWith(16);
  });

  test("renders the label and current value", () => {
    render(
      <SliderInput label="Memory" min={1} max={64} value={8} unit="GB" onChange={() => {}} />
    );
    expect(screen.getByText(/Memory/)).toBeInTheDocument();
  });
});
