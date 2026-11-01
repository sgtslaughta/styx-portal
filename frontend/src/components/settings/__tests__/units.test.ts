import { describe, expect, test } from "vitest";
import { fromDisplay, toDisplay } from "../units";

describe("units", () => {
  test("seconds scale per key and reverse", () => {
    expect(toDisplay("BAN_DURATION", 86400)).toEqual({ value: 24, unit: "hours" });
    expect(fromDisplay("BAN_DURATION", 24)).toBe(86400);
    expect(toDisplay("LOCKOUT_DURATION", 900)).toEqual({ value: 15, unit: "min" });
    expect(toDisplay("REFRESH_TTL", 604800)).toEqual({ value: 7, unit: "days" });
    expect(toDisplay("ACCESS_TTL", 900)).toEqual({ value: 15, unit: "min" });
  });
  test("rate strings", () => {
    expect(toDisplay("RATE_LIMIT_AUTH", "5/60")).toEqual({ value: 5, unit: "per min" });
    expect(toDisplay("X", "10/3600").unit).toBe("per hour");
    expect(toDisplay("X", "10/1").unit).toBe("per sec");
  });
  test("unknown key passes through", () => {
    expect(toDisplay("FOO", 7)).toEqual({ value: 7, unit: "" });
  });
});
