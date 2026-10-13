/** The three layouts of the app. `app-root.styles.ts` uses the same
 * two widths in its media queries. Keep the values equal. */
export type AppLayout = "phone" | "tablet" | "desktop";

export const TABLET_MEDIA_QUERY = "(min-width: 700px)";
export const DESKTOP_MEDIA_QUERY = "(min-width: 1200px)";

/**
 * Tells the app which layout applies, and calls back when that
 * changes. The phone layout renders one tab at a time, and each layout
 * draws the EQ chart at its own size, so the app needs this answer in
 * JavaScript and not only in CSS.
 *
 * Call `current()` to read the layout now, and `subscribe()` to follow
 * later changes. It depends on `window.matchMedia`.
 */
export interface LayoutQuery {
  current(): AppLayout;
  subscribe(onChange: (layout: AppLayout) => void): () => void;
}

function readLayout(): AppLayout {
  if (typeof window === "undefined") {
    return "desktop";
  }
  if (window.matchMedia(DESKTOP_MEDIA_QUERY).matches) {
    return "desktop";
  }
  return window.matchMedia(TABLET_MEDIA_QUERY).matches ? "tablet" : "phone";
}

export const browserLayoutQuery: LayoutQuery = {
  current: readLayout,
  subscribe(onChange: (layout: AppLayout) => void): () => void {
    if (typeof window === "undefined") {
      return () => {};
    }
    const lists = [
      window.matchMedia(TABLET_MEDIA_QUERY),
      window.matchMedia(DESKTOP_MEDIA_QUERY),
    ];
    const listener = (): void => onChange(readLayout());
    for (const list of lists) {
      list.addEventListener("change", listener);
    }
    return () => {
      for (const list of lists) {
        list.removeEventListener("change", listener);
      }
    };
  },
};
