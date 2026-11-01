import { describe, expect, it } from "vitest";
import { rankCats, splitCats } from "../catalog-cats";

describe("catalog categories", () => {
  it("splits comma-joined tags and trims", () => {
    expect(splitCats("Media Servers, Music,Music")).toEqual(["Media Servers", "Music"]);
    expect(splitCats(null)).toEqual([]);
  });
  it("ranks tags by frequency, ties alphabetical", () => {
    expect(rankCats(["Music,Media", "Media", "Books", "Audio"])).toEqual(["Media", "Audio", "Books", "Music"]);
  });
});
