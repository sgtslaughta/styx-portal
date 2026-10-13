import { describe, test, expect } from "vitest";
import { serverFieldErrors } from "../service-validation";

describe("serverFieldErrors", () => {
  test("maps a 422 pydantic list onto fields", () => {
    const r = serverFieldErrors({ status: 422, detail: [
      { loc: ["body", "upstream_url"], msg: "Value error, upstream_url must be http(s)://host" },
      { loc: ["body"], msg: "Value error, something global" },
    ] });
    expect(r.fields).toEqual({ upstream_url: "upstream_url must be http(s)://host" });
    expect(r.rest).toEqual(["something global"]);
  });
  test("maps 409 to slug and 400 container error to container", () => {
    expect(serverFieldErrors({ status: 409, detail: "Slug already in use" }).fields).toEqual({ slug: "Slug already in use" });
    expect(serverFieldErrors({ status: 400, detail: "Container not found among discoverable containers" }).fields.container)
      .toMatch(/not found/);
  });
  test("unknown errors fall through", () => {
    expect(serverFieldErrors(new Error("boom"))).toEqual({ fields: {}, rest: ["boom"] });
  });
});
