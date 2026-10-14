import { expect, test } from "@playwright/test";
import { ADMIN, apiCall, eventually, headerLines, isWhoami, openSettings, uiLogin } from "./helpers";

// http://revproxy answers 404 to every Host except app.proxy.test, which it forwards to whoami.
test("url service behind a name-based reverse proxy gets the site hostname as Host", async ({ browser }) => {
  const ctx = await browser.newContext();
  const p = await ctx.newPage();
  await uiLogin(p, ADMIN);
  await expect(p.getByRole("button", { name: "Settings", exact: true })).toBeVisible();
  await openSettings(p, "Services");
  await p.getByRole("button", { name: "Add service" }).first().click();
  const form = p.getByRole("dialog").filter({ has: p.locator("#ack-origin") });
  await form.locator("#name").fill("Behind proxy");
  await form.locator("#slug").fill("revproxy");
  await form.locator("#upstream").fill("http://revproxy");
  await form.getByLabel("media", { exact: true }).check();
  await form.getByLabel("Upstream is a reverse proxy").click();
  await form.getByLabel("Site hostname").fill("app.proxy.test");
  await expect(form.getByRole("alert").filter({ hasText: "Links may leave Styx" })).toBeVisible();
  await form.locator("#ack-origin").check();
  await form.getByRole("button", { name: "Save" }).click();
  await expect(form).toBeHidden();
  try {
    await eventually(async () => {
      const res = await p.request.get("/revproxy/");
      expect(isWhoami(await res.text())).toBe(true);
    });
    const body = await (await p.request.get("/revproxy/")).text();
    expect(headerLines(body, "Host")).toEqual(["app.proxy.test"]);
    // docs/SERVICES.md promises the Styx (browser) name survives in X-Forwarded-Host
    expect(headerLines(body, "X-Forwarded-Host")).toEqual(["127.0.0.1:18080"]);
  } finally {
    const all: { id: string; slug: string }[] = await apiCall(ctx, "GET", "/api/services");
    const svc = all.find((x) => x.slug === "revproxy");
    if (svc) await apiCall(ctx, "DELETE", `/api/services/${svc.id}`);
    await ctx.close();
  }
});
