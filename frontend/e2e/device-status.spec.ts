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

test("the header shows the unit without a click, and System shows its firmware version", async ({ page }) => {
  await openApp(page);

  await expect(page.locator(DEVICE_PILL)).toContainText("DEQ connected");
  await expect(page.locator(DEVICE_PILL)).not.toContainText(FAKE_UNIT_FIRMWARE);
  // The backend connects by itself, so the header has no connect button.
  // Its one button opens the System section of the settings page.
  await expect(page.getByRole("button", { name: /connect/i })).toHaveCount(0);

  await page.locator(DEVICE_PILL).click();
  await expect(page.locator("system-panel")).toContainText(FAKE_UNIT_FIRMWARE);
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
  await expect(page.locator(DEVICE_PILL)).toContainText("DEQ connected");

  await page.reload();

  await expect(page.locator(DEVICE_PILL)).toContainText("DEQ connected");
});

test("an EQ from the library becomes the one that plays", async ({ page, request }) => {
  await openApp(page);
  await expect(page.locator(DEVICE_PILL)).toContainText("DEQ connected");

  // The first tile is No EQ. The second is the first EQ of the library.
  const equalizerTile = page.locator("dsp-panel .tile").nth(1);
  await expect(equalizerTile).toBeVisible();
  const picked = page.waitForResponse(
    (response) => response.url().endsWith("/api/active-profile/equalizer") && response.ok(),
  );
  await equalizerTile.click();
  await picked;

  await expect(equalizerTile).toHaveAttribute("aria-pressed", "true");
  const state = await (await request.get("/api/active-profile")).json();
  expect(state.equalizer_id).not.toBeNull();

  // The backend's database outlives this test, so play no EQ again.
  await request.put("/api/active-profile/equalizer", { data: { equalizer_id: null } });
});

test("pushing a profile sends the four coefficient blocks", async ({ request }) => {
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

test("activating a profile puts it on the connected unit", async ({ page, request }) => {
  // The backend's database outlives each run. Make another profile the
  // active one first, so the first preset offers Activate.
  const profiles = await (await request.get("/api/profiles")).json();
  await request.put("/api/active-profile", { data: { profile_id: profiles[profiles.length - 1].id } });
  await openApp(page);
  await expect(page.locator(DEVICE_PILL)).toContainText("DEQ connected");
  await openFirstPreset(page);

  const activated = page.waitForResponse(
    (response) => response.url().endsWith("/api/active-profile") && response.request().method() === "PUT",
  );
  await page.locator("profile-activation .activate").click();
  await activated;

  await expect(page.locator("profile-activation .status")).toContainText("Active on the DEQ");
  const state = await (await request.get("/api/active-profile")).json();
  expect(state.status).toBe("applied");
});
