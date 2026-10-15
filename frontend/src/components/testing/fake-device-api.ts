import type { DeviceApi } from "../../api/client.ts";
import type {
  ActiveProfileDto,
  AudioStateDto,
  DeviceDto,
  DeviceOptionsDto,
} from "../../dto/profile.dto.ts";

/** The two value sets the real unit offers, shortened for a test. The
 * backend reads the full lists out of the Pioneer app.
 *
 * Every member here is one the real app shows. The backend leaves out
 * `UNKNOWN`, and the panel leaves out the members Pioneer never shipped
 * a label for, so a fake that carried one of those would make a test
 * disagree with what a person sees. */
const FAKE_OPTIONS: DeviceOptionsDto = {
  eq_styles: [
    { name: "FLAT", wire_value: 2 },
    { name: "SUPER_BASS", wire_value: 3 },
    { name: "POWERFUL", wire_value: 4 },
  ],
  live_simulations: [
    { name: "OFF", wire_value: 1 },
    { name: "CONCERT_HALL", wire_value: 2 },
    { name: "CLUB", wire_value: 4 },
  ],
  audio_sources: [
    { name: "STAND_ALONE", wire_value: 0 },
    { name: "CAR_SOURCE", wire_value: 3 },
    { name: "THROUGH", wire_value: 4 },
  ],
};

const DEFAULT_AUDIO_STATE: AudioStateDto = {
  source_mode: "THROUGH",
  source_mode_wire: 4,
  volume_db: -20,
  muted: false,
  mute_state_wire: 0,
  driving: false,
};

const DISCONNECTED: DeviceDto = {
  connected: false,
  firmware_version: null,
  serial: null,
  problem: null,
};

const CONNECTED: DeviceDto = {
  connected: true,
  firmware_version: "2.02",
  serial: "ABIV002781EW",
  problem: null,
};

/**
 * An in-memory `DeviceApi` fixture: real behaviour, no network, no mocking.
 *
 * It answers as a unit the backend can reach, and it records what the app
 * asked it to send. You set `unreachable` to make the request fail the way
 * an out-of-reach bridge does.
 */
export class FakeDeviceApi implements DeviceApi {
  /** Set to make every call reject, the way `fetch` does when the phone
   * is not on the bridge's network. That is a different state from a
   * bridge that answers and reports the unit as down. */
  unreachable = false;

  pushedProfileIds: number[] = [];
  selectedEqStyles: string[] = [];
  selectedLiveSimulations: string[] = [];
  /** How many times the app asked what the unit is doing with sound. */
  audioReads = 0;
  volumeWrites: number[] = [];
  audioSourceWrites: string[] = [];

  private device: DeviceDto = DISCONNECTED;
  private audio: AudioStateDto = DEFAULT_AUDIO_STATE;

  /** Starts already connected, the way a backend that connects by itself
   * looks to the app by the time it asks. */
  startConnected(): this {
    this.device = CONNECTED;
    return this;
  }

  /** Reports the unit as down, with a reason, as the backend does when it
   * reached the unit and the unit refused. */
  startWithUnitDown(problem: string): this {
    this.device = { ...DISCONNECTED, problem };
    return this;
  }

  async readDevice(): Promise<DeviceDto> {
    this.failIfUnreachable();
    return this.device;
  }

  private failIfUnreachable(): void {
    if (this.unreachable) {
      throw new TypeError("Failed to fetch");
    }
  }

  async connectDevice(): Promise<DeviceDto> {
    this.device = CONNECTED;
    return this.device;
  }

  async disconnectDevice(): Promise<DeviceDto> {
    this.device = DISCONNECTED;
    return this.device;
  }

  async readDeviceOptions(): Promise<DeviceOptionsDto> {
    return FAKE_OPTIONS;
  }

  async writeTuning(profileId: number): Promise<DeviceDto> {
    this.pushedProfileIds = [...this.pushedProfileIds, profileId];
    return this.device;
  }

  /** The profile the app activated, in the order it asked. */
  activatedProfileIds: number[] = [];
  /** What the backend reports. A test sets it to show another status. */
  activeProfile: ActiveProfileDto = {
    profile_id: null,
    status: "none",
    problem: null,
    equalizer_id: null,
    source_mode: "CAR_SOURCE",
  };
  /** The EQs the app picked, in order. `null` means "No EQ". */
  activatedEqualizerIds: (number | null)[] = [];

  async readActiveProfile(): Promise<ActiveProfileDto> {
    this.failIfUnreachable();
    return this.activeProfile;
  }

  /** Behaves as the backend does: a connected unit gets the profile at
   * once, and a unit that is not connected gets it on the next connect. */
  async activateProfile(profileId: number): Promise<ActiveProfileDto> {
    this.failIfUnreachable();
    this.activatedProfileIds = [...this.activatedProfileIds, profileId];
    this.activeProfile = {
      ...this.activeProfile,
      profile_id: profileId,
      status: this.device.connected ? "applied" : "waiting",
      problem: null,
    };
    return this.activeProfile;
  }

  async activateEqualizer(equalizerId: number | null): Promise<ActiveProfileDto> {
    this.failIfUnreachable();
    this.activatedEqualizerIds = [...this.activatedEqualizerIds, equalizerId];
    this.activeProfile = { ...this.activeProfile, equalizer_id: equalizerId };
    return this.activeProfile;
  }

  async selectEqStyle(name: string): Promise<DeviceDto> {
    this.selectedEqStyles = [...this.selectedEqStyles, name];
    return this.device;
  }

  async selectLiveSimulation(name: string): Promise<DeviceDto> {
    this.selectedLiveSimulations = [...this.selectedLiveSimulations, name];
    return this.device;
  }

  async readAudioState(): Promise<AudioStateDto> {
    this.audioReads += 1;
    this.failIfUnreachable();
    return this.audio;
  }

  async setVolume(volumeDb: number): Promise<AudioStateDto> {
    this.failIfUnreachable();
    this.volumeWrites = [...this.volumeWrites, volumeDb];
    this.audio = { ...this.audio, volume_db: volumeDb };
    return this.audio;
  }

  async setAudioSource(name: string): Promise<AudioStateDto> {
    this.failIfUnreachable();
    this.audioSourceWrites = [...this.audioSourceWrites, name];
    this.audio = { ...this.audio, source_mode: name };
    return this.audio;
  }
}
