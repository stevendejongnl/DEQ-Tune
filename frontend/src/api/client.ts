import typia from "typia";
import type {
  AudioSourceWriteDto,
  AudioStateDto,
  BridgeDto,
  DeviceDto,
  DeviceOptionsDto,
  EqStyleWriteDto,
  FavoriteWriteDto,
  LiveSimulationWriteDto,
  ProfileCreateDto,
  ProfileDto,
  ProfileUpdateDto,
  UnitProfileCreateDto,
  VolumeWriteDto,
} from "../dto/profile.dto.ts";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** A fetch-compatible function. Lets tests inject a fake instead of mocking `fetch`. */
export type FetchLike = (url: string, init?: RequestInit) => Promise<Response>;

/** Calls the real `fetch` as a method on `window`. A bare reference to
 * `fetch` loses that binding and throws "Illegal invocation" in browsers. */
function windowFetch(url: string, init?: RequestInit): Promise<Response> {
  return window.fetch(url, init);
}

function buildRequestInit(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  };
}

function assertOk(response: Response, method: string, path: string): void {
  if (!response.ok) {
    throw new ApiError(response.status, `${method} ${path} failed: ${response.status}`);
  }
}

async function readJsonBody(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return undefined;
  }
  return response.json();
}

/** What app-root depends on. DeqApiClient implements it against the real
 * backend, and tests inject a small hand-written fake instead. */
export interface ProfileApi {
  listProfiles(): Promise<ProfileDto[]>;
  getProfile(id: number): Promise<ProfileDto>;
  createProfile(body: ProfileCreateDto): Promise<ProfileDto>;
  updateProfile(id: number, body: ProfileUpdateDto): Promise<ProfileDto>;
  deleteProfile(id: number): Promise<void>;
  duplicateProfile(id: number): Promise<ProfileDto>;
  /** Stars or unstars a profile. A starred preset shows in the sidebar. */
  setFavorite(id: number, favorite: boolean): Promise<ProfileDto>;
  /** Reads the tune the unit holds now and stores it as a custom profile. */
  saveUnitProfile(name: string): Promise<ProfileDto>;
}

/** The unit, as the backend presents it. The backend owns the USB link,
 * so the client uses plain HTTP. Tests inject a hand-written fake. */
export interface DeviceApi {
  readDevice(): Promise<DeviceDto>;
  connectDevice(): Promise<DeviceDto>;
  disconnectDevice(): Promise<DeviceDto>;
  readDeviceOptions(): Promise<DeviceOptionsDto>;
  readAudioState(): Promise<AudioStateDto>;
  setVolume(volumeDb: number): Promise<AudioStateDto>;
  setAudioSource(name: string): Promise<AudioStateDto>;
  writeTuning(profileId: number): Promise<DeviceDto>;
  selectEqStyle(name: string): Promise<DeviceDto>;
  selectLiveSimulation(name: string): Promise<DeviceDto>;
}

/** What the app can ask about the machine holding the link.
 *
 * Separate from `DeviceApi` because it answers a different question. The
 * DEQ being off is normal. The bridge being unwell is a fault.
 */
export interface BridgeApi {
  readBridge(): Promise<BridgeDto>;
}

export class DeqApiClient implements ProfileApi, DeviceApi, BridgeApi {
  private baseUrl: string;
  private fetchImpl: FetchLike;

  constructor(baseUrl: string = "/api", fetchImpl: FetchLike = windowFetch) {
    this.baseUrl = baseUrl;
    this.fetchImpl = fetchImpl;
  }

  private async call(method: string, path: string, body?: unknown): Promise<unknown> {
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, buildRequestInit(method, body));
    assertOk(response, method, path);
    return readJsonBody(response);
  }

  async listProfiles(): Promise<ProfileDto[]> {
    return typia.assert<ProfileDto[]>(await this.call("GET", "/profiles"));
  }

  async getProfile(id: number): Promise<ProfileDto> {
    return typia.assert<ProfileDto>(await this.call("GET", `/profiles/${id}`));
  }

  async createProfile(body: ProfileCreateDto): Promise<ProfileDto> {
    const validBody = typia.assert<ProfileCreateDto>(body);
    return typia.assert<ProfileDto>(await this.call("POST", "/profiles", validBody));
  }

  async updateProfile(id: number, body: ProfileUpdateDto): Promise<ProfileDto> {
    const validBody = typia.assert<ProfileUpdateDto>(body);
    return typia.assert<ProfileDto>(await this.call("PUT", `/profiles/${id}`, validBody));
  }

  async deleteProfile(id: number): Promise<void> {
    await this.call("DELETE", `/profiles/${id}`);
  }

  async duplicateProfile(id: number): Promise<ProfileDto> {
    return typia.assert<ProfileDto>(await this.call("POST", `/profiles/${id}/duplicate`));
  }

  async setFavorite(id: number, favorite: boolean): Promise<ProfileDto> {
    const validBody = typia.assert<FavoriteWriteDto>({ favorite });
    return typia.assert<ProfileDto>(await this.call("PUT", `/profiles/${id}/favorite`, validBody));
  }

  async saveUnitProfile(name: string): Promise<ProfileDto> {
    const validBody = typia.assert<UnitProfileCreateDto>({ name });
    return typia.assert<ProfileDto>(await this.call("POST", "/device/profile", validBody));
  }

  async readDevice(): Promise<DeviceDto> {
    return typia.assert<DeviceDto>(await this.call("GET", "/device"));
  }

  async readBridge(): Promise<BridgeDto> {
    return typia.assert<BridgeDto>(await this.call("GET", "/bridge"));
  }

  async connectDevice(): Promise<DeviceDto> {
    return typia.assert<DeviceDto>(await this.call("POST", "/device/connect"));
  }

  async disconnectDevice(): Promise<DeviceDto> {
    return typia.assert<DeviceDto>(await this.call("POST", "/device/disconnect"));
  }

  async readAudioState(): Promise<AudioStateDto> {
    return typia.assert<AudioStateDto>(await this.call("GET", "/device/audio"));
  }

  async setVolume(volumeDb: number): Promise<AudioStateDto> {
    const body: VolumeWriteDto = { volume_db: volumeDb };
    return typia.assert<AudioStateDto>(await this.call("POST", "/device/volume", body));
  }

  async setAudioSource(name: string): Promise<AudioStateDto> {
    const body: AudioSourceWriteDto = { name };
    return typia.assert<AudioStateDto>(
      await this.call("POST", "/device/audio-source", body),
    );
  }

  async readDeviceOptions(): Promise<DeviceOptionsDto> {
    return typia.assert<DeviceOptionsDto>(await this.call("GET", "/device/options"));
  }

  async writeTuning(profileId: number): Promise<DeviceDto> {
    return typia.assert<DeviceDto>(await this.call("POST", `/device/tuning/${profileId}`));
  }

  async selectEqStyle(name: string): Promise<DeviceDto> {
    const validBody = typia.assert<EqStyleWriteDto>({ name });
    return typia.assert<DeviceDto>(await this.call("POST", "/device/eq-style", validBody));
  }

  async selectLiveSimulation(name: string): Promise<DeviceDto> {
    const validBody = typia.assert<LiveSimulationWriteDto>({ name });
    return typia.assert<DeviceDto>(
      await this.call("POST", "/device/live-simulation", validBody),
    );
  }
}
