import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import type { OpenMode, Workstation } from "@/api/client";
import type { Instance } from "@/lib/types";

const { ApiErr } = vi.hoisted(() => ({
  ApiErr: class extends Error { status: number; constructor(m: string, s: number) { super(m); this.status = s; } },
}));
const connectUrl = vi.fn();
vi.mock("@/api/client", () => ({ api: { workstationConnectUrl: (...a: unknown[]) => connectUrl(...a) }, ApiError: ApiErr }));
const choose = vi.fn((_g: string, _n: string, run: (m: string) => void) => run("new_tab"));
vi.mock("@/components/open-prompt", () => ({ useOpenChoice: () => choose }));
const openPending = vi.fn((_m: string, _l: string, get: () => Promise<string>) => get());
vi.mock("@/lib/connect-wipe", () => ({ openPending: (...a: Parameters<typeof openPending>) => openPending(...a) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

import { useWorkstationConnect } from "../use-workstation-connect";
import { useInstanceConnect } from "../use-instance-connect";

const studio = { id: "w9", name: "Studio", status: "online", in_use: false, in_use_self: false, in_use_by: null } as unknown as Workstation;

function Harness({ ws, mode }: { ws: Workstation; mode?: OpenMode }) {
  const c = useWorkstationConnect();
  return (
    <>
      <button onClick={() => c.connect(ws, mode)}>go</button>
      {c.error && <p role="alert">{c.error}</p>}
      {c.dialog}
    </>
  );
}
function InstHarness({ inst }: { inst: Instance }) {
  const open = useInstanceConnect();
  return <button onClick={() => open(inst)}>open</button>;
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  connectUrl.mockResolvedValue({ url: "/w/studio/" });
});

test("free workstation: asks via the Workspaces preference, connects, remembers it", async () => {
  render(<Harness ws={studio} />);
  fireEvent.click(screen.getByText("go"));
  expect(choose).toHaveBeenCalledWith("workspaces", "Studio", expect.any(Function));
  expect(openPending.mock.calls[0]![1]).toBe("Connecting to Studio…");
  await waitFor(() => expect(connectUrl).toHaveBeenCalledWith("w9", false));
  expect(JSON.parse(localStorage.getItem("styx.home.recent")!)).toEqual({ kind: "workstation", id: "w9" });
});

test("an explicit mode skips the preference prompt", () => {
  render(<Harness ws={studio} mode="new_tab" />);
  fireEvent.click(screen.getByText("go"));
  expect(choose).not.toHaveBeenCalled();
  expect(openPending.mock.calls[0]![0]).toBe("new_tab");
});

test("in use by someone else: Join confirms shared control, then forces", async () => {
  render(<Harness ws={{ ...studio, in_use: true, in_use_by: "bob" }} />);
  fireEvent.click(screen.getByText("go"));
  expect(await screen.findByText('Join "Studio"?')).toBeInTheDocument();
  expect(screen.getByText(/you will both see and control the same screen/)).toBeInTheDocument();
  expect(openPending).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Join" }));
  await waitFor(() => expect(connectUrl).toHaveBeenCalledWith("w9", true));
});

test("seat taken meanwhile (423) turns into the Join confirm", async () => {
  connectUrl.mockRejectedValueOnce(new ApiErr("In use by bob", 423));
  render(<Harness ws={studio} />);
  fireEvent.click(screen.getByText("go"));
  expect(await screen.findByText('Join "Studio"?')).toBeInTheDocument();
});

test("other errors show their message", async () => {
  connectUrl.mockRejectedValueOnce(new Error("Workstation is offline, not online"));
  render(<Harness ws={studio} />);
  fireEvent.click(screen.getByText("go"));
  expect(await screen.findByRole("alert")).toHaveTextContent("Workstation is offline");
});

test("instance connect opens /i/<subdomain>/ and remembers it", async () => {
  render(<InstHarness inst={{ id: "i1", name: "Desk", subdomain: "desk" } as unknown as Instance} />);
  fireEvent.click(screen.getByText("open"));
  expect(choose).toHaveBeenCalledWith("workspaces", "Desk", expect.any(Function));
  expect(openPending.mock.calls[0]![1]).toBe("Launching Desk…");
  await expect(openPending.mock.results[0]!.value).resolves.toBe("/i/desk/");
  expect(JSON.parse(localStorage.getItem("styx.home.recent")!)).toEqual({ kind: "instance", id: "i1" });
});
