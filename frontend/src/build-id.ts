// Vite's `define` replaces this name at build time. See vite.config.ts.
declare const __DEQ_BUILD_ID__: string;

/** The id of the build that this page came from. */
export const BUILD_ID: string = __DEQ_BUILD_ID__;
