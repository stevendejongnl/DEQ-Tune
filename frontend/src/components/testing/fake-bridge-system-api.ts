import type { BridgeSystemApi } from "../../api/client.ts";
import type { BridgeSystemDto } from "../../dto/profile.dto.ts";

/** A Pi Zero 2 W in the car, with its access point up. */
export function sampleBridgeSystem(overrides: Partial<BridgeSystemDto> = {}): BridgeSystemDto {
  return {
    hostname: "deq",
    model: "Raspberry Pi Zero 2 W Rev 1.0",
    operating_system: "Debian GNU/Linux 12 (bookworm)",
    kernel: "6.6.51+rpt-rpi-v8",
    architecture: "aarch64",
    python_version: "3.13.1",
    uptime_seconds: 3720,
    load_average: [0.12, 0.34, 0.56],
    cpu_count: 4,
    cpu_temperature_celsius: 48.3,
    cpu_frequency_mhz: 1000,
    throttled_flags: "0x0",
    memory_total_bytes: 400 * 1024 * 1024,
    memory_available_bytes: 100 * 1024 * 1024,
    swap_total_bytes: 100 * 1024 * 1024,
    swap_free_bytes: 100 * 1024 * 1024,
    backend_memory_bytes: 50 * 1024 * 1024,
    disk_total_bytes: 32 * 1024 ** 3,
    disk_free_bytes: 24 * 1024 ** 3,
    frontend_build: "test-build",
    interfaces: [
      {
        name: "wlan0",
        state: "UP",
        mac_address: "b8:27:eb:00:00:01",
        addresses: ["192.168.4.1/24"],
        received_bytes: 2048,
        sent_bytes: 4096,
        signal_dbm: -61,
      },
    ],
    ...overrides,
  };
}

/**
 * An in-memory `BridgeSystemApi`: real behaviour, no network, no mocking.
 *
 * It answers with `system`. Set `unreachable` to make the request fail, as
 * a Pi that is off does. It counts the reads, so a test can prove a refresh.
 */
export class FakeBridgeSystemApi implements BridgeSystemApi {
  unreachable = false;
  readCount = 0;
  system: BridgeSystemDto = sampleBridgeSystem();

  async readBridgeSystem(): Promise<BridgeSystemDto> {
    this.readCount += 1;
    if (this.unreachable) {
      throw new TypeError("Failed to fetch");
    }
    return this.system;
  }
}
