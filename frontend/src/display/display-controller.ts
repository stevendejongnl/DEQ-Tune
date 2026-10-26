import type { LocaleStorage } from "../i18n/locale.ts";
import { browserLocaleStorage } from "../i18n/browser-locale-storage.ts";
import {
  applyDisplay,
  browserDisplayEnvironment,
  LIGHT_SCHEME_QUERY,
  MORE_CONTRAST_QUERIES,
  readDisplayChoices,
  resolveDisplay,
  saveDisplayChoices,
  type DisplayChoices,
  type DisplayEnvironment,
  type ResolvedDisplay,
} from "./display-mode.ts";

/** Calls `onChange` each time one of the media queries flips. A test passes
 * one that keeps the callback, to flip it by hand. */
export type WatchFunction = (mediaQueries: string[], onChange: () => void) => void;

const watchMediaQueries: WatchFunction = (mediaQueries, onChange) => {
  if (typeof window.matchMedia !== "function") {
    return;
  }
  for (const query of mediaQueries) {
    window.matchMedia(query).addEventListener("change", onChange);
  }
};

/**
 * Keeps the page's display mode in step with the person's choices and the
 * device.
 *
 * Call `start()` once, before the app renders, so the page does not flash
 * dark before it goes light. Call `choose()` from Settings → Display. It
 * depends on a storage for the choices, a `DisplayEnvironment`, the root
 * element and a `WatchFunction`.
 */
export class DisplayController {
  private readonly storage: LocaleStorage;
  private readonly environment: DisplayEnvironment;
  private readonly root: HTMLElement;
  private readonly watch: WatchFunction;
  private current: DisplayChoices;

  constructor(storage: LocaleStorage, environment: DisplayEnvironment, root: HTMLElement, watch: WatchFunction) {
    this.storage = storage;
    this.environment = environment;
    this.root = root;
    this.watch = watch;
    this.current = readDisplayChoices(storage);
  }

  get choices(): DisplayChoices {
    return this.current;
  }

  /** What the page shows now. */
  resolved(): ResolvedDisplay {
    return resolveDisplay(this.current, this.environment);
  }

  start(): void {
    this.apply();
    this.watch([LIGHT_SCHEME_QUERY, ...MORE_CONTRAST_QUERIES], () => this.apply());
  }

  choose(change: Partial<DisplayChoices>): void {
    this.current = { ...this.current, ...change };
    saveDisplayChoices(this.storage, this.current);
    this.apply();
  }

  /** Sets the data attributes, and the browser's own bar colour to match
   * the page. */
  private apply(): void {
    applyDisplay(this.resolved(), this.root);
    const themeColor = this.root.ownerDocument.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
    const background = getComputedStyle(this.root).getPropertyValue("--color-background").trim();
    if (themeColor !== null && background !== "") {
      themeColor.content = background;
    }
  }
}

/** The one controller of the page. */
export const displayController = new DisplayController(
  browserLocaleStorage,
  browserDisplayEnvironment,
  document.documentElement,
  watchMediaQueries,
);
