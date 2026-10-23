import type { DeviceApi, EqualizerApi, ProfileApi } from "../../api/client.ts";
import type {
  ActiveProfileDto,
  AudioStateDto,
  DeviceDto,
  DeviceOptionsDto,
  EqualizerCreateDto,
  EqualizerDto,
  EqualizerUpdateDto,
  ProfileCreateDto,
  ProfileDto,
  ProfileUpdateDto,
  TuningDataDto,
} from "../../dto/profile.dto.ts";
import { FakeDeviceApi } from "./fake-device-api.ts";

/**
 * An in-memory fixture for both halves of the API: real behaviour, no
 * network, no mocking.
 *
 * `app-root` takes one object that serves profiles and the unit, so this
 * holds a `FakeDeviceApi` and forwards the device calls to it. Read
 * `device` in a test to see what the app sent to the unit.
 */
export class FakeProfileApi implements ProfileApi, DeviceApi, EqualizerApi {
  readonly device = new FakeDeviceApi();

  /** The tune the fake unit holds. `null` means no unit answers, so
   * `saveUnitProfile` fails the way the backend's 503 does. */
  unitTuning: TuningDataDto | null = null;

  /** Set to make the profile list reject, the way `fetch` does when the
   * bridge is out of reach. */
  profilesUnreachable = false;

  private profiles: ProfileDto[];
  private nextId: number;

  constructor(initialProfiles: ProfileDto[]) {
    this.profiles = initialProfiles;
    this.nextId = Math.max(0, ...initialProfiles.map((profile) => profile.id)) + 1;
  }

  readDevice(): Promise<DeviceDto> {
    return this.device.readDevice();
  }

  connectDevice(): Promise<DeviceDto> {
    return this.device.connectDevice();
  }

  disconnectDevice(): Promise<DeviceDto> {
    return this.device.disconnectDevice();
  }

  readDeviceOptions(): Promise<DeviceOptionsDto> {
    return this.device.readDeviceOptions();
  }

  writeTuning(profileId: number): Promise<DeviceDto> {
    return this.device.writeTuning(profileId);
  }

  selectEqStyle(name: string): Promise<DeviceDto> {
    return this.device.selectEqStyle(name);
  }

  selectLiveSimulation(name: string): Promise<DeviceDto> {
    return this.device.selectLiveSimulation(name);
  }

  readActiveProfile(): Promise<ActiveProfileDto> {
    return this.device.readActiveProfile();
  }

  activateProfile(profileId: number): Promise<ActiveProfileDto> {
    return this.device.activateProfile(profileId);
  }

  activateEqualizer(equalizerId: number | null): Promise<ActiveProfileDto> {
    return this.device.activateEqualizer(equalizerId);
  }

  /** The EQ library, as the backend keeps it. A test sets it directly. */
  equalizers: EqualizerDto[] = [];

  async listEqualizers(): Promise<EqualizerDto[]> {
    return this.equalizers;
  }

  /** How many EQs the app created. A test reads it to see that quick
   * edits made one copy, not several. */
  createdEqualizers = 0;

  async createEqualizer(body: EqualizerCreateDto): Promise<EqualizerDto> {
    this.createdEqualizers += 1;
    const created: EqualizerDto = {
      id: Math.max(0, ...this.equalizers.map((equalizer) => equalizer.id)) + 1,
      name: body.name,
      source: "custom",
      favorite: false,
      gains: [...body.gains],
    };
    this.equalizers = [...this.equalizers, created];
    return created;
  }

  async setEqualizerFavorite(id: number, favorite: boolean): Promise<EqualizerDto> {
    const updated: EqualizerDto = { ...this.requireEqualizer(id), favorite };
    this.equalizers = this.equalizers.map((equalizer) => (equalizer.id === id ? updated : equalizer));
    return updated;
  }

  async updateEqualizer(id: number, body: EqualizerUpdateDto): Promise<EqualizerDto> {
    const updated: EqualizerDto = { ...this.requireEqualizer(id), ...body };
    this.equalizers = this.equalizers.map((equalizer) => (equalizer.id === id ? updated : equalizer));
    return updated;
  }

  async deleteEqualizer(id: number): Promise<void> {
    this.requireEqualizer(id);
    this.equalizers = this.equalizers.filter((equalizer) => equalizer.id !== id);
  }

  private requireEqualizer(id: number): EqualizerDto {
    const equalizer = this.equalizers.find((candidate) => candidate.id === id);
    if (equalizer === undefined) {
      throw new Error(`No fake EQ with id ${id}`);
    }
    return equalizer;
  }

  readAudioState(): Promise<AudioStateDto> {
    return this.device.readAudioState();
  }

  setVolume(volumeDb: number): Promise<AudioStateDto> {
    return this.device.setVolume(volumeDb);
  }

  setAudioSource(name: string): Promise<AudioStateDto> {
    return this.device.setAudioSource(name);
  }

  private requireProfile(id: number): ProfileDto {
    const profile = this.profiles.find((candidate) => candidate.id === id);
    if (profile === undefined) {
      throw new Error(`No fake profile with id ${id}`);
    }
    return profile;
  }

  async listProfiles(): Promise<ProfileDto[]> {
    if (this.profilesUnreachable) {
      throw new TypeError("Did not find the deq-tune bridge nearby");
    }
    return this.profiles;
  }

  async getProfile(id: number): Promise<ProfileDto> {
    return this.requireProfile(id);
  }

  async createProfile(body: ProfileCreateDto): Promise<ProfileDto> {
    const created: ProfileDto = {
      id: this.nextId++,
      name: body.name,
      source: "custom",
      brand_name: body.brand_name ?? null,
      car_model: body.car_model ?? null,
      speaker_type: body.speaker_type ?? null,
      supported_processors: body.supported_processors ?? [],
      favorite: false,
      data: body.data,
    };
    this.profiles = [...this.profiles, created];
    return created;
  }

  async updateProfile(id: number, body: ProfileUpdateDto): Promise<ProfileDto> {
    const updated: ProfileDto = { ...this.requireProfile(id), ...body };
    this.profiles = this.profiles.map((profile) => (profile.id === id ? updated : profile));
    return updated;
  }

  async deleteProfile(id: number): Promise<void> {
    this.requireProfile(id);
    this.profiles = this.profiles.filter((profile) => profile.id !== id);
  }

  async setFavorite(id: number, favorite: boolean): Promise<ProfileDto> {
    const updated: ProfileDto = { ...this.requireProfile(id), favorite };
    this.profiles = this.profiles.map((profile) => (profile.id === id ? updated : profile));
    return updated;
  }

  async saveUnitProfile(name: string): Promise<ProfileDto> {
    if (this.unitTuning === null) {
      throw new Error("the unit is not connected");
    }
    const saved: ProfileDto = {
      id: this.nextId++,
      name,
      source: "custom",
      brand_name: null,
      car_model: null,
      speaker_type: null,
      supported_processors: [],
      favorite: false,
      data: this.unitTuning,
    };
    this.profiles = [...this.profiles, saved];
    return saved;
  }

  async duplicateProfile(id: number): Promise<ProfileDto> {
    const source = this.requireProfile(id);
    const copy: ProfileDto = {
      ...source,
      id: this.nextId++,
      name: `${source.name} (copy)`,
      source: "custom",
      favorite: false,
    };
    this.profiles = [...this.profiles, copy];
    return copy;
  }
}
