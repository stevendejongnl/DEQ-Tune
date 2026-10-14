import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/**
 * The device flow, through a real browser and a real backend.
 *
 * The backend runs with `DEQ_TRANSPORT=fake`, so the unit on the other end
 * is the fake DEQ, which answers with the replies measured from a real
 * DEQ-S1000A2. The backend connects to it by itself, and the header only
 * reports the link. A pass here means the whole path works: the backend's
 * own connection reaches the header, and a click in the app reaches the unit.
 */

/** The app is one web component tree, so every locator reaches into shadow
 * DOM. Playwright pierces shadow roots for CSS selectors, so a plain CSS
 * selector finds the pill. */
const DEVICE_PILL = "device-status device-pill";
const PILL_DOT = "device-status .dot";

/** The firmware version that the real unit reported in the captured
 * accessory string. The fake DEQ reports the same one. */
const FAKE_UNIT_FIRMWARE = "2.02";

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

/** Opens the first preset. The presets live in the library until a person
 * stars one, so the sidebar alone may show none. */
async function openFirstPreset(page: Page): Promise<void> {
  await page.locator("profile-list .open-library").click();
  await page.locator("profile-list .model-row .chip").first().click();
}

/** Waits until the backend reports a live link. The backend retries every
 * few seconds, so a test that dropped the link waits here for the retry. */
async function waitForTheBackendToConnect(request: APIRequestContext): Promise<void> {
  await expect
    .poll(async () => (await (await request.get("/api/device")).json()).connected)
    .toBe(true);
}

/** Reads the colour that a CSS token resolves to, in the form that
 * `getComputedStyle` returns, so a test can compare it to a computed colour. */
async function resolveColourToken(page: Page, tokenName: string): Promise<string> {
  return page.evaluate((name) => {
    const probe = document.createElement("div");
    probe.style.backgroundColor = `var(${name})`;
    document.body.append(probe);
    const resolved = getComputedStyle(probe).backgroundColor;
    probe.remove();
    return resolved;
  }, tokenName);
}

test.beforeEach(async ({ request }) => {
  // The backend keeps one unit for the whole process, and one test drops
  // the link on purpose. Each test starts once the backend has it again.
  await waitForTheBackendToConnect(request);
});

test("the app loads with no console errors of its own", async ({ page }) => {
  const consoleErrors = await openApp(page);
  await expect(page.locator("app-root")).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test("the header shows the unit and its firmware version without a click", async ({ page }) => {
  await openApp(page);

  await expect(page.locator(DEVICE_PILL)).toContainText("DEQ connected");
  await expect(page.locator(DEVICE_PILL)).toContainText(FAKE_UNIT_FIRMWARE);
  await expect(page.locator("device-status button")).toHaveCount(0);
});

test("the backend connects again by itself after the link drops", async ({ request }) => {
  const dropped = await (await request.post("/api/device/disconnect")).json();
  expect(dropped.connected).toBe(false);

  await waitForTheBackendToConnect(request);
});

test("the pill's dot has the accent colour while connected", async ({ page }) => {
  await openApp(page);
  await expect(page.locator(DEVICE_PILL)).toContainText("DEQ connected");

  // The nested CSS rule `:host([linkstate="connected"]) & { }` sets this
  // colour, and jsdom cannot parse that rule. Only a real browser can check it.
  const dotColour = await page
    .locator(PILL_DOT)
    .evaluate((element) => getComputedStyle(element).backgroundColor);
  expect(dotColour).toBe(await resolveColourToken(page, "--color-accent"));
});

test("the connected state survives a reload, because the backend holds it", async ({ page }) => {
  await openApp(page);
  await expect(page.locator(DEVICE_PILL)).toContainText(FAKE_UNIT_FIRMWARE);

  await page.reload();

  await expect(page.locator(DEVICE_PILL)).toContainText("DEQ connected");
});

test("an EQ style choice reaches the unit", async ({ page }) => {
  await openApp(page);
  await expect(page.locator(DEVICE_PILL)).toContainText(FAKE_UNIT_FIRMWARE);
  await openFirstPreset(page);

  const styleTile = page.locator("dsp-panel .tile").first();
  await expect(styleTile).toBeVisible();
  const pushed = page.waitForResponse(
    (response) => response.url().includes("/api/device/eq-style") && response.ok(),
  );
  await styleTile.click();

  expect((await pushed).status()).toBe(200);
});

test("pushing a profile sends the three coefficient blocks", async ({ request }) => {
  const profiles = await (await request.get("/api/profiles")).json();
  const response = await request.post(`/api/device/tuning/${profiles[0].id}`);

  expect(response.status()).toBe(200);
  expect(await response.json()).toMatchObject({ connected: true });
});

test("the unit's option lists are the app's own, not a shortened copy", async ({ request }) => {
  const options = await (await request.get("/api/device/options")).json();

  // The app's 21 EQ styles and 8 live-simulation modes, read from the
  // Pioneer APK, without the `UNKNOWN` value that a decoder returns.
  expect(options.eq_styles).toHaveLength(20);
  expect(options.live_simulations).toHaveLength(7);
});


test("a star from the library keeps a preset in the sidebar after a reload", async ({ page }) => {
  await openApp(page);
  await page.locator("profile-list .open-library").click();
  const firstRow = page.locator("profile-list .model-row").first();
  const modelName = (await firstRow.locator(".model-name").textContent())!.trim();
  const starred = page.waitForResponse(
    (response) => response.url().includes("/favorite") && response.ok(),
  );
  await firstRow.locator(".star").click();
  await starred;

  await page.reload();

  const sidebarRow = page.locator("profile-list .favorite-list .model-row", { hasText: modelName });
  await expect(sidebarRow).toBeVisible();

  // The backend's database outlives this test, so take the star off again.
  const unstarred = page.waitForResponse(
    (response) => response.url().includes("/favorite") && response.ok(),
  );
  await sidebarRow.locator(".star").click();
  await unstarred;
});
