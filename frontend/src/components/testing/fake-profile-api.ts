import type { DeviceApi, ProfileApi } from "../../api/client.ts";
import type {
  AudioStateDto,
  DeviceDto,
  DeviceOptionsDto,
  ProfileCreateDto,
  ProfileDto,
  ProfileUpdateDto,
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
export class FakeProfileApi implements ProfileApi, DeviceApi {
  readonly device = new FakeDeviceApi();

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

  async duplicateProfile(id: number): Promise<ProfileDto> {
    const source = this.requireProfile(id);
    const copy: ProfileDto = { ...source, id: this.nextId++, name: `${source.name} (copy)`, source: "custom" };
    this.profiles = [...this.profiles, copy];
    return copy;
  }
}
