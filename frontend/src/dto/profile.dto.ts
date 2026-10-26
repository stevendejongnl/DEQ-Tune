// Data Transfer Objects for the DEQ backend API.
// Mirrors backend/app/eq_data.py and backend/app/schemas.py. Keep them in
// sync. The client validates these at the API boundary with typia (see
// ../api/client.ts). Do not trust a value typed as one of these without
// going through that boundary first.

export interface LRBank {
  isLocked: boolean;
  numOfBand: number;
  selectedBank: number;
  banks: number[][];
}

export interface ChannelBankData {
  q: number[];
  f0: number[];
  gain: number[];
}

export interface ChannelBank {
  isLocked: boolean;
  numOfBand: number;
  selectedBank: number;
  banks: ChannelBankData;
}

export interface FoundationEq {
  isLRMode: boolean;
  eqs: Record<string, LRBank>;
  expandEq: Record<string, ChannelBank>;
}

export interface Speaker {
  isPositivePhase: boolean;
  levelDB: number;
  timeAlignmentCm: number;
  levelDBExtended: number;
}

export interface FilterBand {
  cutoff_hpf: number;
  slope_hpf: number;
}

export interface Filter {
  front: FilterBand;
  rear: FilterBand;
}

export interface CancellingEq {
  L: number[];
  R: number[];
}

export interface CancellingTA {
  L: number;
  R: number;
}

export interface FactoryCancel {
  available: boolean;
  enabled: boolean;
  data: {
    cancellingEQ: CancellingEq;
    cancellingTACm: CancellingTA;
  };
}

export interface FaderBalance {
  fader: number;
  balance: number;
}

export interface TimeAlignment {
  enabled: boolean;
  easySoundFitModeEnabled: boolean;
  easySoundFitMode: number;
}

export interface TuningDataDto {
  foundationEq: FoundationEq;
  speakers: Record<string, Speaker>;
  filter: Filter;
  factoryCancel: FactoryCancel;
  faderBalance: FaderBalance;
  timeAlignment: TimeAlignment;
}

export type ProfileSource = "factory" | "custom";

export interface ProfileDto {
  id: number;
  name: string;
  source: ProfileSource;
  brand_name: string | null;
  car_model: string | null;
  speaker_type: string | null;
  supported_processors: string[];
  /** A starred profile shows in the sidebar. The rest stay in the library. */
  favorite: boolean;
  data: TuningDataDto;
}

/** Whether the unit plays the active profile now.
 * - `none`: no profile is active.
 * - `waiting`: the unit is not connected. The profile goes on when it connects.
 * - `applied`: the unit plays this profile, as it is stored now.
 * - `outdated`: the unit is connected but plays an older version, or none.
 * - `failed`: the last push failed, and `problem` says why. */
export type ActiveStatus = "none" | "waiting" | "applied" | "outdated" | "failed";

export interface ActiveProfileDto {
  profile_id: number | null;
  status: ActiveStatus;
  problem: string | null;
  /** The EQ that plays on top of the car profile, or null for none. */
  equalizer_id: number | null;
  /** The source mode each new link gets, as an AUDIO_SOURCE name. */
  source_mode: string;
}

export interface ActiveEqualizerWriteDto {
  equalizer_id: number | null;
}

/** A music-style EQ: 13 gains in dB that play on top of the car profile.
 * A factory EQ is read-only. Copy it to make your own. */
export interface EqualizerDto {
  id: number;
  name: string;
  source: ProfileSource;
  /** A starred EQ shows in the EQ panel and the car app. An EQ of the
   * person's own shows either way. */
  favorite: boolean;
  gains: number[];
}

export interface EqualizerCreateDto {
  name: string;
  gains: number[];
}

export interface EqualizerUpdateDto {
  name?: string;
  gains?: number[];
}

export interface ActiveProfileWriteDto {
  profile_id: number;
}

export interface FavoriteWriteDto {
  favorite: boolean;
}

export interface ProfileCreateDto {
  name: string;
  data: TuningDataDto;
  brand_name?: string | null;
  car_model?: string | null;
  speaker_type?: string | null;
  supported_processors?: string[];
}

/** The name for a profile read from the unit's own tune. */
export interface UnitProfileCreateDto {
  name: string;
}

export interface ProfileUpdateDto {
  name?: string;
  data?: TuningDataDto;
}

// The unit itself. The backend owns the USB link, so the frontend reads
// these over HTTP instead of talking to the device.

export interface DeviceDto {
  connected: boolean;
  firmware_version: string | null;
  serial: string | null;
  problem: string | null;
}

/**
 * What the unit does with sound, read live from it.
 *
 * Separate from `DeviceDto` on purpose. The header polls `DeviceDto`, and
 * that read never opens a link. Every field here costs a request and a
 * reply over USB. Ask for it when someone is looking at it.
 */
export interface AudioStateDto {
  source_mode: string;
  source_mode_wire: number;
  volume_db: number;
  muted: boolean;
  mute_state_wire: number;
  driving: boolean;
}

export interface VolumeWriteDto {
  volume_db: number;
}

export interface AudioSourceWriteDto {
  name: string;
}

export interface DeqEnumValueDto {
  name: string;
  wire_value: number;
}

export interface DeviceOptionsDto {
  eq_styles: DeqEnumValueDto[];
  live_simulations: DeqEnumValueDto[];
  audio_sources: DeqEnumValueDto[];
}

export interface EqStyleWriteDto {
  name: string;
}

export interface LiveSimulationWriteDto {
  name: string;
}

/** One fault the bridge recorded after it started.
 *
 * A notice stays until the bridge restarts, so it can describe something
 * that is no longer happening. The bridge keeps it on purpose: a power dip
 * that lasted a second still explains a link that dropped.
 */
export interface BridgeNoticeDto {
  key: string;
  severity: string;
  message: string;
  first_seen_seconds: number;
  last_seen_seconds: number;
  count: number;
}

/** The machine holding the link, which is not the DEQ.
 *
 * The undervoltage fields are null where the machine cannot tell: a
 * laptop has no `vcgencmd`, and false would be a claim it cannot make.
 */
export interface BridgeDto {
  undervoltage_now: boolean | null;
  undervoltage_since_boot: boolean | null;
  uptime_seconds: number | null;
  notices: BridgeNoticeDto[];
}

/** One network interface of the bridge, without loopback. Only a wireless
 * interface has a signal. */
export interface NetworkInterfaceDto {
  name: string;
  state: string;
  mac_address: string | null;
  addresses: string[];
  received_bytes: number | null;
  sent_bytes: number | null;
  signal_dbm: number | null;
}

/** The bridge's machine statistics, for the system dialog.
 *
 * Each field is null where the machine cannot tell. `frontend_build` is the
 * build id of the frontend that the bridge serves now.
 */
export interface BridgeSystemDto {
  hostname: string | null;
  model: string | null;
  operating_system: string | null;
  kernel: string | null;
  architecture: string | null;
  python_version: string | null;
  uptime_seconds: number | null;
  load_average: number[] | null;
  cpu_count: number | null;
  cpu_temperature_celsius: number | null;
  cpu_frequency_mhz: number | null;
  throttled_flags: string | null;
  memory_total_bytes: number | null;
  memory_available_bytes: number | null;
  swap_total_bytes: number | null;
  swap_free_bytes: number | null;
  backend_memory_bytes: number | null;
  disk_total_bytes: number | null;
  disk_free_bytes: number | null;
  frontend_build: string | null;
  interfaces: NetworkInterfaceDto[];
}

/** A network that the bridge joins. `connected` is true while the bridge
 * uses it. */
export interface SavedWifiNetworkDto {
  ssid: string;
  connected: boolean;
}

/** A network in range, from the bridge's last scan. `signal` is 0 to 100. */
export interface VisibleWifiNetworkDto {
  ssid: string;
  signal: number;
  secured: boolean;
}

export interface WifiDto {
  saved: SavedWifiNetworkDto[];
  visible: VisibleWifiNetworkDto[];
}

/** An empty password saves an open network. */
export interface WifiNetworkWriteDto {
  ssid: string;
  password: string;
}

export interface WifiForgetWriteDto {
  ssid: string;
}

/** A custom profile in a library file. It has no id: the importing
 * database gives it a new one. */
export interface LibraryProfileDto {
  name: string;
  brand_name: string | null;
  car_model: string | null;
  speaker_type: string | null;
  supported_processors: string[];
  favorite: boolean;
  data: TuningDataDto;
}

export interface LibraryEqualizerDto {
  name: string;
  favorite: boolean;
  gains: number[];
}

/** A person's own library as one file. See backend/app/library_transfer.py. */
export interface LibraryExportDto {
  format: "deq-tune-library";
  version: number;
  profiles: LibraryProfileDto[];
  equalizers: LibraryEqualizerDto[];
  starred_factory_profiles: string[];
  starred_factory_equalizers: string[];
}

export interface LibraryImportDto {
  profiles_added: number;
  equalizers_added: number;
  skipped: number;
  stars_added: number;
}

/** The Pi's own access point. It never carries the key. */
export interface AccessPointDto {
  ssid: string;
  uses_default_key: boolean;
}

/** A new access point key. The Pi restarts a few seconds after the reply,
 * so the key applies. */
export interface AccessPointKeyWriteDto {
  key: string;
}

export interface UpdateHistoryDto {
  from_version: string;
  to_version: string;
  at: string;
}

/** What the Pi's release updater last found. `supported` is false on a
 * machine with no updater, such as a laptop. */
export interface UpdatesDto {
  supported: boolean;
  installed: string | null;
  latest: string | null;
  automatic: boolean;
  update_available: boolean;
  gadget_pending: boolean;
  notes: string;
  release_url: string;
  checked_at: string;
  last_result: string;
  history: UpdateHistoryDto[];
  /** The build id of the web app that the bridge serves now, or null. */
  frontend_build: string | null;
}

export interface UpdateSettingsWriteDto {
  automatic: boolean;
}

/** The BLE bridge's pairing window. A new phone can bond only while
 * `pairing_open` is true. `supported` is false on a machine with no bridge,
 * such as a laptop. */
export interface BluetoothPairingDto {
  supported: boolean;
  pairing_open: boolean;
  seconds_left: number;
  window_seconds: number;
  pair_at_car_start: boolean;
  bonded_phones: string[];
}

export interface BluetoothSettingsWriteDto {
  pair_at_car_start: boolean;
}

/** One filter of the unit's crossover. `cutoff_position` indexes
 * `cutoffs_hz`. `slope` is the filter order: 0 is Pass, 1 to 4 are 6 to
 * 24 dB per octave. A car profile owns the front and rear filters, and the
 * unit keeps the others. */
export interface CrossoverFilterDto {
  speaker: "front" | "rear" | "rear_subwoofer" | "subwoofer";
  kind: "high_pass" | "low_pass";
  owner: "profile" | "unit";
  cutoff_position: number;
  slope: number;
  cutoffs_hz: number[];
}

/** A speaker mode this app can move the unit to. */
export type StandardSpeakerMode =
  | "STANDARD_FL_FR"
  | "STANDARD_FL_FR_RL_RR"
  | "STANDARD_FL_FR_RL_RR_SW"
  | "STANDARD_FL_FR_RLSW_RRSW"
  | "STANDARD_FL_FR_SW";

/** The filters that the unit's speaker mode uses, in slot order, and the
 * modes a person can switch to. */
export interface CrossoverDto {
  speaker_mode: string;
  speaker_modes: StandardSpeakerMode[];
  filters: CrossoverFilterDto[];
}

/** The speaker mode to move the unit to. */
export interface SpeakerModeWriteDto {
  speaker_mode: StandardSpeakerMode;
}

/** A new setting for one filter that the unit keeps. */
export interface CrossoverFilterWriteDto {
  speaker: "rear_subwoofer" | "subwoofer";
  cutoff_position: number;
  slope: number;
}
