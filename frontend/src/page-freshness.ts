import type { BridgeSystemDto } from "./dto/profile.dto.ts";

/**
 * Where the page that a person looks at came from.
 *
 * - `live`: the Pi answers, and serves this build.
 * - `cached`: the Pi does not answer. The service worker served this copy.
 * - `outdated`: the Pi answers, but serves another build. A reload gets it.
 */
export type PageFreshness = "live" | "cached" | "outdated";

/** `system` is null when the Pi did not answer. A Pi with no build file (a
 * dev server, with Vite in front) has nothing to compare, so it is live. */
export function readPageFreshness(system: BridgeSystemDto | null, pageBuild: string): PageFreshness {
  if (system === null) {
    return "cached";
  }
  if (system.frontend_build === null || system.frontend_build === pageBuild) {
    return "live";
  }
  return "outdated";
}
