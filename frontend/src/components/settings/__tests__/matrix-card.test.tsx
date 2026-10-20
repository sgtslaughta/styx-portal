import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, test, expect, vi, beforeEach } from "vitest";

const matrixStatus = vi.fn();
const matrixGenerate = vi.fn();
const matrixActivate = vi.fn();
const matrixRemove = vi.fn();
vi.mock("@/api/client", () => ({
  api: {
    matrixStatus: (...a: unknown[]) => matrixStatus(...a),
    matrixGenerate: (...a: unknown[]) => matrixGenerate(...a),
    matrixActivate: (...a: unknown[]) => matrixActivate(...a),
    matrixRemove: (...a: unknown[]) => matrixRemove(...a),
  },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(m: string, s: number) { super(m); this.status = s; }
  },
}));
vi.mock("@/lib/matrix-image", () => ({
  drawCard: vi.fn(),
  cardPngBlob: vi.fn().mockResolvedValue(new Blob(["x"])),
}));

import { ApiError } from "@/api/client";
import { MatrixCard } from "../matrix-card";

function renderIt() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MatrixCard /></QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  URL.createObjectURL = vi.fn(() => "blob:x");
  URL.revokeObjectURL = vi.fn();
  window.print = vi.fn();
});

describe("MatrixCard", () => {
  test("generate -> shows card, warning, confirm cell; activate calls API", async () => {
    matrixStatus.mockResolvedValueOnce({ enabled: false }).mockResolvedValue({ enabled: true });
    matrixGenerate.mockResolvedValue({ cells: { A1: "XYZ" }, confirm_cell: "C7" });
    matrixActivate.mockResolvedValue({ enabled: true });
    renderIt();
    fireEvent.click(await screen.findByRole("button", { name: "Generate card" }));
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "pw" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText(/shown once. Save or print it now/)).toBeTruthy();
    expect(screen.getByText(/Enter cell C7 to activate/)).toBeTruthy();
    expect(matrixGenerate).toHaveBeenCalledWith("pw");
    fireEvent.click(screen.getByRole("button", { name: "Print" }));
    expect(window.print).toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Cell value"), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Activate" }));
    await waitFor(() => expect(matrixActivate).toHaveBeenCalledWith("abc"));
    expect(await screen.findByText("Active")).toBeTruthy();
  });

  test("remove asks for password", async () => {
    matrixStatus.mockResolvedValue({ enabled: true });
    matrixRemove.mockResolvedValue(undefined);
    renderIt();
    fireEvent.click(await screen.findByRole("button", { name: "Remove" }));
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "pw" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() => expect(matrixRemove).toHaveBeenCalledWith("pw"));
  });

  test("401 on status shows session expired; 401 on generate is wrong password", async () => {
    matrixStatus.mockRejectedValue(new ApiError("x", 401));
    renderIt();
    expect(await screen.findByText("Your session expired — sign in again.")).toBeTruthy();
  });

  test("wrong password on generate", async () => {
    matrixStatus.mockResolvedValue({ enabled: false });
    matrixGenerate.mockRejectedValue(new ApiError("bad", 401));
    renderIt();
    fireEvent.click(await screen.findByRole("button", { name: "Generate card" }));
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "no" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("Incorrect password.")).toBeTruthy();
  });
});
