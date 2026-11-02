import { expect, type Page } from "@playwright/test";
import { MEMBER, SHOTS, openSettings, setTheme } from "./helpers";

const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "mobile", width: 390, height: 844 },
] as const;
const THEMES = ["light", "dark"] as const;

async function shot(page: Page, name: string, fullPage = true) {
  await page.waitForTimeout(350); // let framer-motion transitions settle
  await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage });
}

/** Scroll every scrollable element inside open dialogs to the bottom. */
async function scrollDialogs(page: Page) {
  await page.evaluate(() => {
    for (const el of document.querySelectorAll<HTMLElement>("[role=dialog] *")) {
      if (el.scrollHeight > el.clientHeight + 4) el.scrollTop = el.scrollHeight;
    }
  });
}

async function serviceDrawer(page: Page, tag: string) {
  await openSettings(page, "Apps");
  await shot(page, `services-list-${tag}`);
  await page.getByRole("button", { name: "Add from running container" }).first().click();
  await expect(page.getByRole("dialog", { name: "Running containers" })).toBeVisible();
  await shot(page, `services-discover-${tag}`, false);
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: "Add service" }).click();
  const form = page.getByRole("dialog").filter({ has: page.locator("#ack-origin") });
  await form.locator("#name").fill("Example");
  await form.locator("#slug").fill("example");
  await form.locator("#upstream").fill("https://192.168.1.10:8443");
  await form.getByText("Advanced", { exact: true }).click();
  await form.locator("#mount").selectOption("cookie-root");
  await form.locator("#auth").selectOption("sso-with-bypass");
  await form.getByRole("button", { name: "Add bypass rule" }).click();
  await form.getByLabel("Bypass path prefix").fill("/api");
  await form.getByLabel("Required header").fill("Authorization");
  await form.getByLabel("Verify upstream TLS").click();
  await shot(page, `service-form-callouts-top-${tag}`, false);
  await scrollDialogs(page);
  await shot(page, `service-form-callouts-bottom-${tag}`, false);
  await form.locator("#auth").selectOption("app-native");
  await shot(page, `service-form-app-native-${tag}`, false);
  await page.keyboard.press("Escape");
  await expect(form).toBeHidden();
}

async function groupsScreens(page: Page, tag: string) {
  await openSettings(page, "Users and groups");
  await shot(page, `groups-panel-${tag}`);
  await openSettings(page, "Users and groups");
  await page.getByRole("row").filter({ hasText: MEMBER.username }).getByRole("button", { name: "More" }).click();
  await page.getByRole("menuitem", { name: /Groups/ }).click();
  await expect(page.getByRole("dialog", { name: `Groups for ${MEMBER.username}` })).toBeVisible();
  await shot(page, `user-groups-dialog-${tag}`, false);
  await page.keyboard.press("Escape");
}

export async function captureAll(admin: Page, member: Page) {
  for (const vp of VIEWPORTS) {
    for (const theme of THEMES) {
      const tag = `${theme}-${vp.name}`;
      for (const p of [admin, member]) {
        await p.setViewportSize({ width: vp.width, height: vp.height });
        await p.goto("/");
        await setTheme(p, theme);
      }
      await member.goto("/");
      await expect(member.getByRole("region", { name: "Apps" })).toBeVisible();
      await shot(member, `home-tiles-member-${tag}`);
      await admin.goto("/");
      await expect(admin.getByRole("region", { name: "Apps" })).toBeVisible();
      await shot(admin, `home-tiles-admin-${tag}`);
      await serviceDrawer(admin, tag);
      await groupsScreens(admin, tag);
    }
  }
  for (const p of [admin, member]) await p.setViewportSize({ width: 1440, height: 900 });
}
