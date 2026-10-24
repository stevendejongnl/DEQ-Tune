import { SETTINGS_SECTIONS, type SettingsSection } from "./components/settings-page.ts";
import { SUPPORTED_LOCALES, type Locale } from "./i18n/locale.ts";

/** The phone layout's bottom tabs, next to Settings. */
export type PhoneTab = "audio" | "eq" | "car";

/** Sound holds what plays: the audio, the EQ and its library. Car holds the
 * car profile: the speakers, their timing and the car's own correction. */
export type AppPage = "sound" | "car" | "settings";

/** Where the person is in the app. `locale` is there only after the person
 * chose a language: the car app's copy and the Pi's page each keep their own
 * saved language, and the hash carries a choice from one to the other. */
export interface PageLocation {
  page: AppPage;
  phoneTab: PhoneTab;
  settingsSection: SettingsSection;
  locale?: Locale;
}

const PAGES: readonly AppPage[] = ["sound", "car", "settings"];
const PHONE_TABS: readonly PhoneTab[] = ["audio", "eq", "car"];

/**
 * Keeps the page location in the URL's hash, so a reload opens the same
 * page. The car app reloads the page on a pull down, and the person
 * expects to stay where they were.
 *
 * Call `read()` for the hash and `write()` to replace it. It depends on
 * `window.location` and `window.history`.
 */
export interface PageLocationStore {
  read(): string;
  write(hash: string): void;
}

export function pageLocationHash(location: PageLocation): string {
  const parameters = new URLSearchParams({
    page: location.page,
    tab: location.phoneTab,
    section: location.settingsSection,
  });
  if (location.locale !== undefined) {
    parameters.set("lang", location.locale);
  }
  return `#${parameters.toString()}`;
}

/** The parts of a hash that name a known page, tab, section or language. */
export function parsePageLocation(hash: string): Partial<PageLocation> {
  const parameters = new URLSearchParams(hash.replace(/^#/, ""));
  const location: Partial<PageLocation> = {};
  const page = parameters.get("page");
  const phoneTab = parameters.get("tab");
  const settingsSection = parameters.get("section");
  const locale = parameters.get("lang");
  if (PAGES.some((known) => known === page)) {
    location.page = page as AppPage;
  }
  if (PHONE_TABS.some((known) => known === phoneTab)) {
    location.phoneTab = phoneTab as PhoneTab;
  }
  if (SETTINGS_SECTIONS.some((known) => known === settingsSection)) {
    location.settingsSection = settingsSection as SettingsSection;
  }
  if (SUPPORTED_LOCALES.some((known) => known === locale)) {
    location.locale = locale as Locale;
  }
  return location;
}

// `replaceState`, not `location.hash`: each tab change would otherwise add a
// history entry, and the car app's back button would walk through them.
export const browserPageLocationStore: PageLocationStore = {
  read: () => (typeof window === "undefined" ? "" : window.location.hash),
  write(hash) {
    if (typeof window !== "undefined") {
      window.history.replaceState(window.history.state, "", hash);
    }
  },
};
