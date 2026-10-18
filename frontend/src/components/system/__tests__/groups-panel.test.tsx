import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, test, expect, vi, beforeEach } from "vitest";

const listGroups = vi.fn();
const listServices = vi.fn();
const deleteGroup = vi.fn();
const createGroup = vi.fn();
const getUserGroups = vi.fn();
const setUserGroups = vi.fn();
vi.mock("@/api/client", () => ({
  api: {
    listGroups: (...a: unknown[]) => listGroups(...a),
    listServices: (...a: unknown[]) => listServices(...a),
    deleteGroup: (...a: unknown[]) => deleteGroup(...a),
    createGroup: (...a: unknown[]) => createGroup(...a),
    getUserGroups: (...a: unknown[]) => getUserGroups(...a),
    setUserGroups: (...a: unknown[]) => setUserGroups(...a),
  },
  ApiError: class extends Error {},
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { GroupsPanel } from "../groups-panel";
import { UserGroupsDialog } from "../user-groups-dialog";

const media = { id: "g1", name: "media", description: null, member_count: 2 };

beforeEach(() => {
  vi.clearAllMocks();
  listGroups.mockResolvedValue([media]);
  listServices.mockResolvedValue([
    { id: "s1", slug: "jellyfin", name: "Jellyfin", allowed_groups: ["media"], enabled: true },
    { id: "s2", slug: "other", name: "Other", allowed_groups: [], enabled: true },
  ]);
  deleteGroup.mockResolvedValue(undefined);
});

describe("GroupsPanel", () => {
  test("lists groups and warns about affected services on delete", async () => {
    render(<GroupsPanel />);
    await waitFor(() => expect(screen.getByText("media")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /delete media/i }));
    const dlg = await screen.findByRole("dialog");
    expect(dlg).toHaveTextContent(/Jellyfin/);
    expect(dlg).not.toHaveTextContent(/Other/);
    expect(dlg).toHaveTextContent(/only admins will be able to open/i);
  });

  test("confirming delete calls the api and reloads", async () => {
    render(<GroupsPanel />);
    await screen.findByText("media");
    fireEvent.click(screen.getByRole("button", { name: /delete media/i }));
    fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
    await waitFor(() => expect(deleteGroup).toHaveBeenCalledWith("g1"));
    await waitFor(() => expect(listGroups).toHaveBeenCalledTimes(2));
  });

  test("shows empty state", async () => {
    listGroups.mockResolvedValue([]);
    render(<GroupsPanel />);
    expect(await screen.findByText(/no groups yet/i)).toBeInTheDocument();
  });

  test("shows error with retry when load fails", async () => {
    listGroups.mockRejectedValueOnce(new Error("boom"));
    render(<GroupsPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/boom/);
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(await screen.findByText("media")).toBeInTheDocument();
  });

  test("create is disabled until a name is typed, then posts trimmed values", async () => {
    createGroup.mockResolvedValue({ ...media, id: "g2", name: "kids" });
    render(<GroupsPanel />);
    await screen.findByText("media");
    const add = screen.getByRole("button", { name: "Add group" });
    expect(add).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Group name"), { target: { value: " kids " } });
    fireEvent.click(add);
    await waitFor(() => expect(createGroup).toHaveBeenCalledWith({ name: "kids", description: null }));
  });
});

describe("UserGroupsDialog", () => {
  test("preselects current groups and saves selection", async () => {
    listGroups.mockResolvedValue([media, { id: "g2", name: "kids", description: null, member_count: 0 }]);
    getUserGroups.mockResolvedValue(["g1"]);
    setUserGroups.mockResolvedValue(["g2"]);
    const onOpenChange = vi.fn();
    render(<UserGroupsDialog userId="u1" username="ann" open onOpenChange={onOpenChange} />);
    const media_cb = await screen.findByRole("checkbox", { name: "media" });
    expect(media_cb).toBeChecked();
    fireEvent.click(media_cb);
    fireEvent.click(screen.getByRole("checkbox", { name: "kids" }));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(setUserGroups).toHaveBeenCalledWith("u1", ["g2"]));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });
});
