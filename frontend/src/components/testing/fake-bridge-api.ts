import type { BridgeApi } from "../../api/client.ts";
import type { BridgeDto, BridgeNoticeDto } from "../../dto/profile.dto.ts";

const HEALTHY: BridgeDto = {
  undervoltage_now: false,
  undervoltage_since_boot: false,
  uptime_seconds: 120,
  notices: [],
};

/**
 * An in-memory `BridgeApi` fixture: real behaviour, no network, no mocking.
 *
 * It answers as a healthy bridge. Call `raiseNotice` to give it a fault,
 * or set `unreachable` to make the request fail. It counts the reads, so a
 * test can prove that the component asked for the bridge state again.
 */
export class FakeBridgeApi implements BridgeApi {
  unreachable = false;
  readCount = 0;

  private bridge: BridgeDto = HEALTHY;

  raiseNotice(notice: Partial<BridgeNoticeDto> = {}): this {
    const full: BridgeNoticeDto = {
      key: "undervoltage",
      severity: "warning",
      message: "The bridge has had a power dip.",
      first_seen_seconds: 10,
      last_seen_seconds: 10,
      count: 1,
      ...notice,
    };
    this.bridge = { ...this.bridge, notices: [...this.bridge.notices, full] };
    return this;
  }

  /** Returns the bridge to health, keeping the notices it already has.
   * That is what the real one does: a notice outlives its cause. */
  recover(): this {
    this.bridge = { ...this.bridge, undervoltage_now: false };
    return this;
  }

  async readBridge(): Promise<BridgeDto> {
    this.readCount += 1;
    if (this.unreachable) {
      throw new TypeError("Failed to fetch");
    }
    return this.bridge;
  }
}
