import type { BridgeSystemDto } from "./dto/profile.dto.ts";

/**
 * Where the page that a person looks at came from.
 *
 * - `live`: the Pi answers, and serves this build.
 * - `offline`: the Pi does not answer. The page shows what it loaded before,
 *   or, in the car app, the copy that the app carries.
 * - `outdated`: the Pi answers, but serves another build. A reload gets it.
 */
export type PageFreshness = "live" | "offline" | "outdated";

/** `system` is null when the Pi did not answer. A Pi with no build file (a
 * dev server, with Vite in front) has nothing to compare, so it is live. */
export function readPageFreshness(system: BridgeSystemDto | null, pageBuild: string): PageFreshness {
  if (system === null) {
    return "offline";
  }
  if (system.frontend_build === null || system.frontend_build === pageBuild) {
    return "live";
  }
  return "outdated";
}
