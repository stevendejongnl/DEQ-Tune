import type { DeviceDto } from "../dto/profile.dto.ts";

/** What the app can see of the link, and nothing more.
 *
 * There are two links. The phone reaches the bridge over Wi-Fi, and the
 * bridge reaches the unit over USB. They fail separately and ask
 * different things of the person reading the pill, so they are different
 * states here. Telling them apart needs no backend change, because the
 * two arrive by different routes: see `readLinkState`.
 */
export type LinkState = "no-bridge" | "unit-down" | "connected";

/** Reads the link state from what one request returned.
 *
 * `null` means the request itself failed, which only happens when the
 * bridge is out of reach. A request that answered and says
 * `connected: false` is the other case: the bridge is there and the unit
 * is not.
 */
export function readLinkState(device: DeviceDto | null): LinkState {
  if (device === null) {
    return "no-bridge";
  }
  return device.connected ? "connected" : "unit-down";
}
