import { render, screen } from "@testing-library/react";
import { MountConsentDialog } from "../mount-consent-dialog";

const base = { target: "/config/config/network.xml", key: "/NetworkConfiguration/BaseUrl", old: "", new: "/jellyfin" };
const show = (changes: (typeof base & { created?: boolean })[]) => render(
  <MountConsentDialog open appName="Jellyfin" changes={changes} onConfirm={() => {}} onCancel={() => {}} />);

it("marks a created file and explains it", () => {
  show([{ ...base, created: true }]);
  expect(screen.getAllByText(/\(new file\)/).length).toBeGreaterThan(0);
  expect(screen.getAllByText("(no file yet)").length).toBeGreaterThan(0);
  expect(screen.queryByText("(not set)")).not.toBeInTheDocument();
  expect(screen.getByText(
    "Styx creates this file. Undoing leaves it with an empty base path, which is Jellyfin's default.",
  )).toBeInTheDocument();
});

it("shows no new-file wording for an existing file", () => {
  show([base]);
  expect(screen.queryByText(/\(new file\)/)).not.toBeInTheDocument();
  expect(screen.queryByText(/Styx creates this file/)).not.toBeInTheDocument();
  expect(screen.getAllByText("(not set)").length).toBeGreaterThan(0);
});
