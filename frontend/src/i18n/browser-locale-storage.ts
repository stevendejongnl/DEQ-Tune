import type { LocaleStorage } from "./locale.ts";

/** LocaleStorage backed by the real `window.localStorage`. Swallows
 * errors (private browsing, disabled storage) rather than breaking the
 * app over a remembered language preference. */
export const browserLocaleStorage: LocaleStorage = {
  getItem(key) {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  setItem(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      // Ignore the failure. Losing the saved preference is not worth failing over.
    }
  },
};
