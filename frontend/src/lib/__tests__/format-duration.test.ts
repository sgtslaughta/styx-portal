import { expect, test } from "vitest";
import { formatDuration } from "../utils";

test.each([
  [null, "—"], [undefined, "—"], [-1, "—"], [Number.NaN, "—"],
  [0, "0s"], [59.9, "59s"], [60, "1m"], [2730, "45m"], [3600, "1h"], [11_520, "3h 12m"],
  [86_400, "1d"], [104_400, "1d 5h"], [536_400, "6d 5h"], [520_200, "6d"],
])("formatDuration(%s) = %s", (input, out) => {
  expect(formatDuration(input as number | null | undefined)).toBe(out);
});
