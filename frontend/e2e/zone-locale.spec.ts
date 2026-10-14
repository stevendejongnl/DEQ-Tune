import { expect, test, type Page } from "@playwright/test";

/** The zone names sit in the EQ editor, which needs a profile open. */
async function openFirstProfile(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.locator("app-root")).toBeVisible();
  // The presets live in the library until a person stars one.
  await page.locator("profile-list .open-library").click();
  await page.locator("profile-list .model-row .chip").first().click();
  // The main EQ chart. The car profile's correction chart sits with the
  // speakers, so a bare "eq-editor" matches two.
  await expect(page.locator("equalizer-editor eq-editor")).toBeVisible();
}

async function openInLocale(page: Page, locale: string): Promise<void> {
  await page.goto("/");
  await page.evaluate((chosen) => localStorage.setItem("deq-tune-locale", chosen), locale);
  await openFirstProfile(page);
}

test("the zone names and hints follow the chosen locale", async ({ page }) => {
  await openInLocale(page, "en");
  await expect(page.getByText("Sub-bass").first()).toBeVisible();
  await expect(page.getByText("Low mids").first()).toBeVisible();
  await expect(page.getByText("Cymbals, detail and sense of space.").first()).toBeAttached();

  await openInLocale(page, "nl");
  await expect(page.getByText("Sublaag").first()).toBeVisible();
  await expect(page.getByText("Laag midden").first()).toBeVisible();

  await openInLocale(page, "ja");
  await expect(page.getByText("超低音").first()).toBeVisible();
});
