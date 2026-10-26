import type { BluetoothApi } from "../../api/client.ts";
import type { BluetoothPairingDto } from "../../dto/profile.dto.ts";

/** What a machine with no BLE bridge answers, such as a laptop. */
export const NO_BRIDGE: BluetoothPairingDto = {
  supported: false,
  pairing_open: false,
  seconds_left: 0,
  window_seconds: 0,
  pair_at_car_start: true,
  bonded_phones: [],
};

/** A Pi whose pairing window is closed, with one bonded phone. */
export function closedPi(overrides: Partial<BluetoothPairingDto> = {}): BluetoothPairingDto {
  return {
    supported: true,
    pairing_open: false,
    seconds_left: 0,
    window_seconds: 300,
    pair_at_car_start: true,
    bonded_phones: ["Pixel 8"],
    ...overrides,
  };
}

/** A BluetoothApi that holds the bridge's state in memory.
 *
 * A window request opens the window at the next read, the way the real
 * bridge takes the request within a second. `failWith` makes every next
 * call throw that error. */
export class FakeBluetoothApi implements BluetoothApi {
  pairing: BluetoothPairingDto;
  failWith: Error | null = null;
  requests = 0;

  constructor(pairing: BluetoothPairingDto = NO_BRIDGE) {
    this.pairing = pairing;
  }

  async readBluetooth(): Promise<BluetoothPairingDto> {
    this.throwIfFailing();
    return this.pairing;
  }

  async setPairAtCarStart(pairAtCarStart: boolean): Promise<BluetoothPairingDto> {
    this.throwIfFailing();
    this.pairing = { ...this.pairing, pair_at_car_start: pairAtCarStart };
    return this.pairing;
  }

  async requestPairingWindow(): Promise<void> {
    this.throwIfFailing();
    this.requests += 1;
    this.pairing = {
      ...this.pairing,
      pairing_open: true,
      seconds_left: this.pairing.window_seconds,
    };
  }

  private throwIfFailing(): void {
    if (this.failWith !== null) {
      throw this.failWith;
    }
  }
}
