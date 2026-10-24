import type { WifiApi } from "../../api/client.ts";
import { ApiError } from "../../api/client.ts";
import type { AccessPointDto, WifiDto } from "../../dto/profile.dto.ts";

/** The default key of `configure-access-point.sh`. */
const DEFAULT_ACCESS_POINT_KEY = "deq-tune-bridge";

/** A WifiApi that holds the networks in memory, and fails on request.
 *
 * `failWith` makes every next call throw that error, the way the real client
 * throws an `ApiError` for a 409 or a 503. */
export class FakeWifiApi implements WifiApi {
  wifi: WifiDto;
  failWith: Error | null = null;
  savedPasswords: string[] = [];
  joinRequests = 0;
  /** The access point's name and key, or null for a Pi without one. */
  accessPoint: { ssid: string; key: string } | null;

  constructor(wifi: WifiDto, accessPoint: { ssid: string; key: string } | null = null) {
    this.wifi = wifi;
    this.accessPoint = accessPoint;
  }

  async readWifi(): Promise<WifiDto> {
    this.throwIfFailing();
    return this.wifi;
  }

  async saveWifiNetwork(ssid: string, password: string): Promise<WifiDto> {
    this.throwIfFailing();
    this.savedPasswords.push(password);
    this.wifi = { ...this.wifi, saved: [...this.wifi.saved, { ssid, connected: false }] };
    return this.wifi;
  }

  async forgetWifiNetwork(ssid: string): Promise<WifiDto> {
    this.throwIfFailing();
    this.wifi = { ...this.wifi, saved: this.wifi.saved.filter((network) => network.ssid !== ssid) };
    return this.wifi;
  }

  async requestWifiJoin(): Promise<void> {
    this.throwIfFailing();
    this.joinRequests += 1;
  }

  async readAccessPoint(): Promise<AccessPointDto> {
    this.throwIfFailing();
    return this.accessPointRead();
  }

  async setAccessPointKey(key: string): Promise<AccessPointDto> {
    this.throwIfFailing();
    if (this.accessPoint !== null) {
      this.accessPoint = { ...this.accessPoint, key };
    }
    return this.accessPointRead();
  }

  private accessPointRead(): AccessPointDto {
    if (this.accessPoint === null) {
      throw new ApiError(404, "The Pi has no access point.");
    }
    return { ssid: this.accessPoint.ssid, uses_default_key: this.accessPoint.key === DEFAULT_ACCESS_POINT_KEY };
  }

  private throwIfFailing(): void {
    if (this.failWith !== null) {
      throw this.failWith;
    }
  }
}
