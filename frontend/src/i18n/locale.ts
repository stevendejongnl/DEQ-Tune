/**
 * The locales the app offers.
 *
 * A new locale needs three edits: this list, its own name in LOCALE_NAMES
 * below, and its catalog in ui-strings.ts. The compiler asks for each one.
 */
export const SUPPORTED_LOCALES = ["en", "ja", "de", "fr", "es", "nl"] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];

/** Each locale's name in that locale. The language picker shows these, so
 * they stay the same text for every reader. */
export const LOCALE_NAMES: Record<Locale, string> = {
  en: "English",
  ja: "日本語",
  de: "Deutsch",
  fr: "Français",
  es: "Español",
  nl: "Nederlands",
};

export const DEFAULT_LOCALE: Locale = "en";

const LOCALE_STORAGE_KEY = "deq-tune-locale";

function isSupportedLocale(value: string): value is Locale {
  return (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

/** The supported locale of a language tag such as "nl-NL", or null. */
export function localeFromLanguageTag(languageTag: string): Locale | null {
  const languageCode = languageTag.split("-")[0].toLowerCase();
  return isSupportedLocale(languageCode) ? languageCode : null;
}

/** Picks the first browser language (e.g. "de-DE", "de") that matches a
 * supported locale, or DEFAULT_LOCALE if none match. */
export function detectBrowserLocale(browserLanguages: readonly string[]): Locale {
  for (const language of browserLanguages) {
    const languageCode = language.split("-")[0].toLowerCase();
    if (isSupportedLocale(languageCode)) {
      return languageCode;
    }
  }
  return DEFAULT_LOCALE;
}

/** What locale.ts needs from browser storage. Lets tests inject an
 * in-memory fake instead of stubbing `window.localStorage`. */
export interface LocaleStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

/** Resolves the locale to start the app in: a previously saved choice if
 * there is one, otherwise the detected browser locale. It saves that
 * detection, so a later visit does not switch without notice if the
 * browser's language list changes. */
export function resolveInitialLocale(
  storage: LocaleStorage,
  browserLanguages: readonly string[],
): Locale {
  const saved = storage.getItem(LOCALE_STORAGE_KEY);
  if (saved !== null && isSupportedLocale(saved)) {
    return saved;
  }

  const detected = detectBrowserLocale(browserLanguages);
  storage.setItem(LOCALE_STORAGE_KEY, detected);
  return detected;
}

export function saveLocale(storage: LocaleStorage, locale: Locale): void {
  storage.setItem(LOCALE_STORAGE_KEY, locale);
}
