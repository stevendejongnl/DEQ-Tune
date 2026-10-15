import typia from "typia";
import type {
  ActiveEqualizerWriteDto,
  ActiveProfileDto,
  ActiveProfileWriteDto,
  AudioSourceWriteDto,
  AudioStateDto,
  BridgeDto,
  BridgeSystemDto,
  DeviceDto,
  DeviceOptionsDto,
  EqualizerCreateDto,
  EqualizerDto,
  EqualizerUpdateDto,
  EqStyleWriteDto,
  FavoriteWriteDto,
  LiveSimulationWriteDto,
  ProfileCreateDto,
  ProfileDto,
  ProfileUpdateDto,
  UnitProfileCreateDto,
  VolumeWriteDto,
  WifiDto,
  WifiForgetWriteDto,
  WifiNetworkWriteDto,
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
  readActiveProfile(): Promise<ActiveProfileDto>;
  /** Makes a profile the one the unit plays. The backend pushes it now when
   * the unit is connected, and on the next connect otherwise. */
  activateProfile(profileId: number): Promise<ActiveProfileDto>;
  /** Picks the EQ on top of the car profile, or none with `null`. */
  activateEqualizer(equalizerId: number | null): Promise<ActiveProfileDto>;
}

/** The EQ library. A factory EQ is read-only, so a person copies it first. */
export interface EqualizerApi {
  listEqualizers(): Promise<EqualizerDto[]>;
  createEqualizer(body: EqualizerCreateDto): Promise<EqualizerDto>;
  setEqualizerFavorite(id: number, favorite: boolean): Promise<EqualizerDto>;
  updateEqualizer(id: number, body: EqualizerUpdateDto): Promise<EqualizerDto>;
  deleteEqualizer(id: number): Promise<void>;
}

/** What the app can ask about the machine holding the link.
 *
 * Separate from `DeviceApi` because it answers a different question. The
 * DEQ being off is normal. The bridge being unwell is a fault.
 */
export interface BridgeApi {
  readBridge(): Promise<BridgeDto>;
}

/** The bridge's machine statistics: memory, disk, network, load and the
 * frontend build it serves. Only the system dialog reads them. */
export interface BridgeSystemApi {
  readBridgeSystem(): Promise<BridgeSystemDto>;
}

/** The Wi-Fi networks that the bridge joins.
 *
 * A save or a forget changes the saved networks only. The bridge joins a
 * saved network on its own, or after `requestWifiJoin`. A 503 means the
 * machine cannot manage Wi-Fi. A 409 means the bridge refused, most often
 * because the DEQ holds the link.
 */
export interface WifiApi {
  readWifi(): Promise<WifiDto>;
  saveWifiNetwork(ssid: string, password: string): Promise<WifiDto>;
  forgetWifiNetwork(ssid: string): Promise<WifiDto>;
  requestWifiJoin(): Promise<void>;
}

export class DeqApiClient implements ProfileApi, DeviceApi, EqualizerApi, BridgeApi, BridgeSystemApi, WifiApi {
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

  async readBridgeSystem(): Promise<BridgeSystemDto> {
    return typia.assert<BridgeSystemDto>(await this.call("GET", "/bridge/system"));
  }

  async readWifi(): Promise<WifiDto> {
    return typia.assert<WifiDto>(await this.call("GET", "/wifi"));
  }

  async saveWifiNetwork(ssid: string, password: string): Promise<WifiDto> {
    const validBody = typia.assert<WifiNetworkWriteDto>({ ssid, password });
    return typia.assert<WifiDto>(await this.call("POST", "/wifi/networks", validBody));
  }

  async forgetWifiNetwork(ssid: string): Promise<WifiDto> {
    const validBody = typia.assert<WifiForgetWriteDto>({ ssid });
    return typia.assert<WifiDto>(await this.call("POST", "/wifi/forget", validBody));
  }

  async requestWifiJoin(): Promise<void> {
    await this.call("POST", "/wifi/join");
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

  async readActiveProfile(): Promise<ActiveProfileDto> {
    return typia.assert<ActiveProfileDto>(await this.call("GET", "/active-profile"));
  }

  async activateProfile(profileId: number): Promise<ActiveProfileDto> {
    const validBody = typia.assert<ActiveProfileWriteDto>({ profile_id: profileId });
    return typia.assert<ActiveProfileDto>(await this.call("PUT", "/active-profile", validBody));
  }

  async activateEqualizer(equalizerId: number | null): Promise<ActiveProfileDto> {
    const validBody = typia.assert<ActiveEqualizerWriteDto>({ equalizer_id: equalizerId });
    return typia.assert<ActiveProfileDto>(
      await this.call("PUT", "/active-profile/equalizer", validBody),
    );
  }

  async listEqualizers(): Promise<EqualizerDto[]> {
    return typia.assert<EqualizerDto[]>(await this.call("GET", "/equalizers"));
  }

  async createEqualizer(body: EqualizerCreateDto): Promise<EqualizerDto> {
    const validBody = typia.assert<EqualizerCreateDto>(body);
    return typia.assert<EqualizerDto>(await this.call("POST", "/equalizers", validBody));
  }

  async setEqualizerFavorite(id: number, favorite: boolean): Promise<EqualizerDto> {
    const validBody = typia.assert<FavoriteWriteDto>({ favorite });
    return typia.assert<EqualizerDto>(
      await this.call("PUT", `/equalizers/${id}/favorite`, validBody),
    );
  }

  async updateEqualizer(id: number, body: EqualizerUpdateDto): Promise<EqualizerDto> {
    const validBody = typia.assert<EqualizerUpdateDto>(body);
    return typia.assert<EqualizerDto>(await this.call("PUT", `/equalizers/${id}`, validBody));
  }

  async deleteEqualizer(id: number): Promise<void> {
    await this.call("DELETE", `/equalizers/${id}`);
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
