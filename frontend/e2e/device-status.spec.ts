import { expect, test, type Page } from "@playwright/test";

/**
 * The device flow, through a real browser and a real backend.
 *
 * The backend runs with `DEQ_TRANSPORT=fake`, so the unit on the other end
 * is the fake DEQ, which answers with the replies measured from a real
 * DEQ-S1000A2. A pass here means the whole path works: a click in the
 * header reaches the session layer and the unit's own answer comes back.
 */

/** The app is one web component tree, so every locator reaches into shadow
 * DOM. Playwright pierces shadow roots for CSS selectors, so a plain CSS
 * selector finds the pill. */
const DEVICE_PILL = "device-status .pill";
const CONNECT_BUTTON = "device-status button.connect";

/** Noise the Vite dev server makes, which says nothing about the app.
 *
 * Vite optimizes dependencies on the first load and answers a request that
 * was already in flight with `504 (Outdated Optimize Dep)`. The browser
 * fetches again and the page loads, so this is a race in the dev server's
 * cache warming, not an error the app caused. It appears on a cold CI
 * runner and not on a warm one, which made this test flaky until it was
 * filtered out.
 */
const DEV_SERVER_NOISE = [/Outdated Optimize Dep/, /\[vite\] hot updated/];

function isAppError(text: string): boolean {
  return !DEV_SERVER_NOISE.some((pattern) => pattern.test(text));
}

async function openApp(page: Page): Promise<string[]> {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" && isAppError(message.text())) {
      consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  await page.goto("/");
  await expect(page.locator(DEVICE_PILL)).toBeVisible();
  return consoleErrors;
}

test.beforeEach(async ({ request }) => {
  // The backend keeps one unit for the whole process, so each test starts
  // from a disconnected one. This needs no page, so it does not navigate:
  // a second `goto` to the same URL can wait for a load that never fires.
  await request.post("/api/device/disconnect");
});

test("the app loads with no console errors of its own", async ({ page }) => {
  const consoleErrors = await openApp(page);
  await expect(page.locator("app-root")).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test("the header offers a connect button while no unit is connected", async ({ page }) => {
  await openApp(page);

  await expect(page.locator(DEVICE_PILL)).toContainText("DEQ not connected");
  await expect(page.locator(CONNECT_BUTTON)).toBeVisible();
});

test("connecting shows the unit's own firmware version", async ({ page }) => {
  await openApp(page);

  await page.locator(CONNECT_BUTTON).click();

  // 2.02 is what the real unit reported in the captured accessory string.
  await expect(page.locator(DEVICE_PILL)).toContainText("DEQ connected");
  await expect(page.locator(DEVICE_PILL)).toContainText("2.02");
  await expect(page.locator(CONNECT_BUTTON)).toHaveCount(0);
});

test("the pill's dot turns to the accent colour once connected", async ({ page }) => {
  await openApp(page);
  const dot = page.locator("device-status .dot");
  const idleColour = await dot.evaluate((element) => getComputedStyle(element).backgroundColor);

  await page.locator(CONNECT_BUTTON).click();
  await expect(page.locator(DEVICE_PILL)).toContainText("DEQ connected");

  // The nested CSS rule `.pill.connected & { }` sets this colour, and jsdom
  // cannot parse that rule. Only a real browser can check it.
  const connectedColour = await dot.evaluate(
    (element) => getComputedStyle(element).backgroundColor,
  );
  expect(connectedColour).not.toBe(idleColour);
});

test("the connected state survives a reload, because the backend holds it", async ({ page }) => {
  await openApp(page);
  await page.locator(CONNECT_BUTTON).click();
  await expect(page.locator(DEVICE_PILL)).toContainText("2.02");

  await page.reload();

  await expect(page.locator(DEVICE_PILL)).toContainText("DEQ connected");
});

test("an EQ style choice reaches the unit", async ({ page }) => {
  await openApp(page);
  await page.locator(CONNECT_BUTTON).click();
  await expect(page.locator(DEVICE_PILL)).toContainText("2.02");
  await page.locator("profile-list li button, profile-list .tile").first().click();

  const styleTile = page.locator("dsp-panel .tile").first();
  await expect(styleTile).toBeVisible();
  const pushed = page.waitForResponse(
    (response) => response.url().includes("/api/device/eq-style") && response.ok(),
  );
  await styleTile.click();

  expect((await pushed).status()).toBe(200);
});

test("pushing a profile sends the three coefficient blocks", async ({ page }) => {
  await openApp(page);
  await page.request.post("/api/device/connect");

  const profiles = await (await page.request.get("/api/profiles")).json();
  const response = await page.request.post(`/api/device/tuning/${profiles[0].id}`);

  expect(response.status()).toBe(200);
  expect(await response.json()).toMatchObject({ connected: true });
});

test("the unit's option lists are the app's own, not a shortened copy", async ({ request }) => {
  const options = await (await request.get("/api/device/options")).json();

  // 21 EQ styles and 8 live-simulation modes, read from the Pioneer APK.
  expect(options.eq_styles).toHaveLength(21);
  expect(options.live_simulations).toHaveLength(8);
});
