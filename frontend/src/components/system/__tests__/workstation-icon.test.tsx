import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, test, expect, vi, beforeEach } from "vitest";
import { toast } from "sonner";
import { WorkstationIconSettings } from "../workstation-icon-settings";
import { WorkstationIcon } from "../workstation-icon";
import { api, type Workstation } from "@/api/client";

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));
vi.mock("@/api/client", () => ({ api: { setWorkstationIcon: vi.fn() } }));

const ws = (o: Partial<Workstation> = {}) =>
  ({ id: "w1", name: "Box", icon_kind: "auto", icon_etag: "abc123", ...o }) as Workstation;
const set = vi.mocked(api.setWorkstationIcon);

beforeEach(() => {
  vi.clearAllMocks();
  set.mockResolvedValue(ws());
});

describe("WorkstationIcon", () => {
  test("img src uses id and etag, decorative", () => {
    const { container } = render(<WorkstationIcon ws={ws()} />);
    const img = container.querySelector("img")!;
    expect(img.getAttribute("src")).toBe("/api/workstations/w1/icon?v=abc123");
    expect(img.getAttribute("alt")).toBe("");
    expect(img.className).toMatch(/h-6 w-6.*rounded-md/);
  });
});

describe("WorkstationIcon fallback", () => {
  test("image error shows uppercase initial tile, no img; resets on etag change", () => {
    const { container, rerender } = render(<WorkstationIcon ws={ws({ name: "game" })} className="size-8" />);
    fireEvent.error(container.querySelector("img")!);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("G")).toBeTruthy();
    rerender(<WorkstationIcon ws={ws({ name: "game", icon_etag: "new" })} className="size-8" />);
    expect(container.querySelector("img")).not.toBeNull();
  });
});

describe("WorkstationIconSettings", () => {
  test("auto mode has no Save button; shows current icon", () => {
    const { container } = render(<WorkstationIconSettings ws={ws({ icon_kind: "emoji" })} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Auto" }));
    expect(screen.queryByRole("button", { name: "Save icon" })).toBeNull();
    expect(container.querySelector("img")!.getAttribute("src")).toBe("/api/workstations/w1/icon?v=abc123");
  });

  test("mode follows icon_kind and src follows icon_etag", () => {
    const { container, rerender } = render(<WorkstationIconSettings ws={ws()} onSaved={vi.fn()} />);
    rerender(<WorkstationIconSettings ws={ws({ icon_kind: "emoji", icon_etag: "zzz" })} onSaved={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Emoji" })).toHaveAttribute("aria-pressed", "true");
    expect(container.querySelector("img")!.getAttribute("src")).toBe("/api/workstations/w1/icon?v=zzz");
  });

  test("clears local emoji after save", async () => {
    render(<WorkstationIconSettings ws={ws()} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Emoji" }));
    fireEvent.change(screen.getByLabelText("Emoji"), { target: { value: "🚀" } });
    fireEvent.click(screen.getByRole("button", { name: "Save icon" }));
    await waitFor(() => expect(screen.getByLabelText("Emoji")).toHaveValue(""));
  });

  test("works without Intl.Segmenter", () => {
    const orig = (Intl as any).Segmenter;
    delete (Intl as any).Segmenter;
    try {
      render(<WorkstationIconSettings ws={ws()} onSaved={vi.fn()} />);
      fireEvent.click(screen.getByRole("button", { name: "Emoji" }));
      fireEvent.change(screen.getByLabelText("Emoji"), { target: { value: "ab" } });
      expect(screen.getByRole("alert").textContent).toBe("Use a single emoji.");
    } finally {
      (Intl as any).Segmenter = orig;
    }
  });

  test("emoji mode saves a single emoji", async () => {
    render(<WorkstationIconSettings ws={ws()} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Emoji" }));
    fireEvent.change(screen.getByLabelText("Emoji"), { target: { value: "🚀" } });
    fireEvent.click(screen.getByRole("button", { name: "Save icon" }));
    await waitFor(() => expect(set).toHaveBeenCalledWith("w1", "emoji", "🚀"));
  });

  test("emoji mode rejects several characters and long sequences", () => {
    render(<WorkstationIconSettings ws={ws()} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Emoji" }));
    const input = screen.getByLabelText("Emoji");
    fireEvent.change(input, { target: { value: "ab" } });
    expect(screen.getByRole("alert").textContent).toBe("Use a single emoji.");
    expect(screen.getByRole("button", { name: "Save icon" })).toBeDisabled();
    fireEvent.change(input, { target: { value: "👨‍👩‍👧" } }); // one grapheme, 18 bytes
    expect(screen.getByRole("alert").textContent).toContain("too long");
  });

  test("image mode previews and saves a data URI", async () => {
    render(<WorkstationIconSettings ws={ws()} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Image" }));
    const file = new File([new Uint8Array([1, 2, 3])], "a.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("Upload image"), { target: { files: [file] } });
    const prev = await screen.findByTestId("icon-preview");
    expect(prev.getAttribute("src")).toMatch(/^data:.*base64,/);
    fireEvent.click(screen.getByRole("button", { name: "Save icon" }));
    await waitFor(() => expect(set).toHaveBeenCalledWith("w1", "image", expect.stringMatching(/^data:.*base64,/)));
  });

  test("rejects images over 256 KB", () => {
    render(<WorkstationIconSettings ws={ws()} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Image" }));
    const big = new File([new Uint8Array(256 * 1024 + 1)], "big.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("Upload image"), { target: { files: [big] } });
    expect(screen.getByRole("alert").textContent).toBe("Images must be 256 KB or smaller.");
    expect(screen.queryByTestId("icon-preview")).toBeNull();
    expect(screen.getByRole("button", { name: "Save icon" })).toBeDisabled();
  });

  test("reset to auto only shows for custom icons and sends auto", async () => {
    const { rerender } = render(<WorkstationIconSettings ws={ws()} onSaved={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Reset to auto" })).toBeNull();
    rerender(<WorkstationIconSettings ws={ws({ icon_kind: "image" })} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Reset to auto" }));
    await waitFor(() => expect(set).toHaveBeenCalledWith("w1", "auto", undefined));
  });

  test("shows backend errors as a toast", async () => {
    set.mockRejectedValue(new Error("Not a valid PNG."));
    render(<WorkstationIconSettings ws={ws()} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Emoji" }));
    fireEvent.change(screen.getByLabelText("Emoji"), { target: { value: "🚀" } });
    fireEvent.click(screen.getByRole("button", { name: "Save icon" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Not a valid PNG."));
  });

  test("error ids are distinct per row", () => {
    render(<>
      <WorkstationIconSettings ws={ws({ id: "a" })} onSaved={vi.fn()} />
      <WorkstationIconSettings ws={ws({ id: "b" })} onSaved={vi.fn()} />
    </>);
    const inputs = [];
    for (const b of screen.getAllByRole("button", { name: "Emoji" })) {
      fireEvent.click(b);
    }
    for (const i of screen.getAllByLabelText("Emoji")) {
      fireEvent.change(i, { target: { value: "ab" } });
      inputs.push(i.getAttribute("aria-describedby"));
    }
    expect(inputs).toEqual(["icon-error-a", "icon-error-b"]);
  });

  test("failed reset keeps the custom mode", async () => {
    set.mockRejectedValue(new Error("nope"));
    render(<WorkstationIconSettings ws={ws({ icon_kind: "emoji" })} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByText("Reset to auto"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("nope"));
    expect(screen.getByText("Emoji").getAttribute("aria-pressed")).toBe("true");
  });
});
