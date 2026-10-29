import { describe, expect, it } from "vitest";
import { pickMedia, scaleDims, MAX_THUMB_W } from "../stream-thumb";

function el(tag: string, w: number, h: number) {
  return { tagName: tag.toUpperCase(), getBoundingClientRect: () => ({ width: w, height: h }) } as unknown as Element;
}
const docOf = (els: Element[]) => ({ querySelectorAll: () => els }) as unknown as Document;

describe("scaleDims", () => {
  it("caps width at 480 keeping aspect", () => {
    expect(scaleDims(1920, 1080)).toEqual({ w: MAX_THUMB_W, h: 270 });
  });
  it("never upscales", () => {
    expect(scaleDims(300, 200)).toEqual({ w: 300, h: 200 });
  });
  it("rejects empty sizes", () => {
    expect(scaleDims(0, 100)).toBeNull();
  });
});

describe("pickMedia", () => {
  it("picks the largest visible element", () => {
    const small = el("canvas", 100, 100);
    const big = el("video", 800, 600);
    expect(pickMedia(docOf([small, big]))).toBe(big);
  });
  it("ignores zero-size elements", () => {
    expect(pickMedia(docOf([el("canvas", 0, 0)]))).toBeNull();
  });
  it("returns null with no media", () => {
    expect(pickMedia(docOf([]))).toBeNull();
  });
});
