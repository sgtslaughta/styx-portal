import { test } from "node:test";
import assert from "node:assert/strict";
import { isPublicPath, resolveDark } from "./resolve.ts";

test("isPublicPath matches public routes and their children", () => {
  assert.equal(isPublicPath("/login"), true);
  assert.equal(isPublicPath("/setup"), true);
  assert.equal(isPublicPath("/accept-invite/abc123"), true);
  assert.equal(isPublicPath("/"), false);
  assert.equal(isPublicPath("/instances"), false);
  // must not match a path that merely starts with the same letters
  assert.equal(isPublicPath("/loginsomething"), false);
});

test("THE BUG: public page with stored 'dark' follows a LIGHT OS, not the stored pref", () => {
  assert.equal(resolveDark("/login", "dark", false), false);
});

test("public page follows the OS in both directions, ignoring stored pref", () => {
  assert.equal(resolveDark("/login", "dark", true), true); // OS dark -> dark
  assert.equal(resolveDark("/login", "light", true), true); // stored light ignored, OS dark
  assert.equal(resolveDark("/setup", "light", false), false);
});

test("authenticated pages honour the stored preference", () => {
  assert.equal(resolveDark("/", "dark", false), true); // stored dark wins on light OS
  assert.equal(resolveDark("/instances", "light", true), false); // stored light wins on dark OS
  assert.equal(resolveDark("/", "system", true), true); // system -> follows OS
  assert.equal(resolveDark("/", null, false), false); // no pref -> system -> light OS
});
