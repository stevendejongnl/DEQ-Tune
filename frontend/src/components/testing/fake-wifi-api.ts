import type { WifiApi } from "../../api/client.ts";
import type { WifiDto } from "../../dto/profile.dto.ts";

/** A WifiApi that holds the networks in memory, and fails on request.
 *
 * `failWith` makes every next call throw that error, the way the real client
 * throws an `ApiError` for a 409 or a 503. */
export class FakeWifiApi implements WifiApi {
  wifi: WifiDto;
  failWith: Error | null = null;
  savedPasswords: string[] = [];
  joinRequests = 0;

  constructor(wifi: WifiDto) {
    this.wifi = wifi;
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

  private throwIfFailing(): void {
    if (this.failWith !== null) {
      throw this.failWith;
    }
  }
}
