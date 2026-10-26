import type { LocaleStorage } from "../i18n/locale.ts";

/**
 * How the app looks: the colour scheme, the contrast, the text size and
 * the reading aid.
 *
 * The first three follow the device by default: the browser's or Android's
 * own setting. A person can fix any of them in Settings → Display, per
 * device, like the language. With no signal from the device, the app stays
 * dark, because it runs in a car, often at night.
 *
 * Easy reading helps people with dyslexia: a typeface made for reading
 * ease and wider spacing. No device signal exists for it, so it is off
 * until a person turns it on.
 */

export type SchemeChoice = "device" | "dark" | "light";
export type ContrastChoice = "device" | "normal" | "more";
export type TextChoice = "device" | "normal" | "large";
export type ReadingChoice = "normal" | "easy";

export interface DisplayChoices {
  scheme: SchemeChoice;
  contrast: ContrastChoice;
  text: TextChoice;
  reading: ReadingChoice;
}

/** What the page shows after the device had its say. */
export interface ResolvedDisplay {
  scheme: "dark" | "light";
  contrast: "normal" | "more";
  text: "normal" | "large";
  reading: ReadingChoice;
}

export const FOLLOW_THE_DEVICE: DisplayChoices = {
  scheme: "device",
  contrast: "device",
  text: "device",
  reading: "normal",
};

/** What the device says. `window.matchMedia` and the browser's default
 * font size give it in a browser. A test passes a fixed one. */
export interface DisplayEnvironment {
  matches(mediaQuery: string): boolean;
  /** The root element's default font size in pixels, before the app sets
   * any. A browser's "large text" setting raises it above 16. */
  defaultFontSizePx(): number;
}

export const LIGHT_SCHEME_QUERY = "(prefers-color-scheme: light)";
export const MORE_CONTRAST_QUERIES = ["(prefers-contrast: more)", "(forced-colors: active)"];

/** A default font size from this one up counts as a request for large text.
 * The browsers' own default is 16 px, and their "large" setting is 20 px. */
export const LARGE_TEXT_FROM_PX = 20;

export function resolveDisplay(choices: DisplayChoices, environment: DisplayEnvironment): ResolvedDisplay {
  return {
    scheme: choices.scheme === "device" ? deviceScheme(environment) : choices.scheme,
    contrast: choices.contrast === "device" ? deviceContrast(environment) : choices.contrast,
    text: choices.text === "device" ? deviceText(environment) : choices.text,
    reading: choices.reading,
  };
}

function deviceScheme(environment: DisplayEnvironment): "dark" | "light" {
  return environment.matches(LIGHT_SCHEME_QUERY) ? "light" : "dark";
}

function deviceContrast(environment: DisplayEnvironment): "normal" | "more" {
  return MORE_CONTRAST_QUERIES.some((query) => environment.matches(query)) ? "more" : "normal";
}

function deviceText(environment: DisplayEnvironment): "normal" | "large" {
  return environment.defaultFontSizePx() >= LARGE_TEXT_FROM_PX ? "large" : "normal";
}

/** Puts the resolved display on the root element as data attributes.
 * `global.css` holds a token set per attribute value. */
export function applyDisplay(display: ResolvedDisplay, root: HTMLElement): void {
  root.dataset.scheme = display.scheme;
  root.dataset.contrast = display.contrast;
  root.dataset.text = display.text;
  root.dataset.reading = display.reading;
}

const STORAGE_KEY = "deq-tune.display";

/** Reads the stored choices. Anything missing or unknown follows the device. */
export function readDisplayChoices(storage: LocaleStorage): DisplayChoices {
  let stored: Partial<Record<keyof DisplayChoices, unknown>> = {};
  try {
    stored = JSON.parse(storage.getItem(STORAGE_KEY) ?? "{}") ?? {};
  } catch {
    stored = {};
  }
  return {
    scheme: oneOf(stored.scheme, ["device", "dark", "light"], "device"),
    contrast: oneOf(stored.contrast, ["device", "normal", "more"], "device"),
    text: oneOf(stored.text, ["device", "normal", "large"], "device"),
    reading: oneOf(stored.reading, ["normal", "easy"], "normal"),
  };
}

export function saveDisplayChoices(storage: LocaleStorage, choices: DisplayChoices): void {
  storage.setItem(STORAGE_KEY, JSON.stringify(choices));
}

function oneOf<Value extends string>(value: unknown, allowed: readonly Value[], fallback: Value): Value {
  return allowed.includes(value as Value) ? (value as Value) : fallback;
}

/** The real environment: `window.matchMedia` and the root's default font
 * size. With no `matchMedia`, nothing matches, so the app stays dark. */
export const browserDisplayEnvironment: DisplayEnvironment = {
  matches(mediaQuery) {
    return typeof window.matchMedia === "function" && window.matchMedia(mediaQuery).matches;
  },
  defaultFontSizePx() {
    const probe = document.createElement("div");
    probe.style.cssText = "position:absolute;visibility:hidden;font-size:medium";
    document.body.append(probe);
    const size = parseFloat(getComputedStyle(probe).fontSize);
    probe.remove();
    return Number.isFinite(size) ? size : 16;
  },
};
