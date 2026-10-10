// Data Transfer Objects for the DEQ backend API.
// Mirrors backend/app/eq_data.py and backend/app/schemas.py — keep in sync.
// Validated at the API boundary with typia (see ../api/client.ts) — do
// not trust a value typed as one of these without going through that
// boundary first.

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
  data: TuningDataDto;
}

export interface ProfileCreateDto {
  name: string;
  data: TuningDataDto;
  brand_name?: string | null;
  car_model?: string | null;
  speaker_type?: string | null;
  supported_processors?: string[];
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
 * What the unit is actually doing with sound, read live from it.
 *
 * Separate from `DeviceDto` on purpose: that one is polled for the header
 * and never opens a link, while every field here costs a request and a
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

/** One fault the bridge has seen since it started.
 *
 * A notice stays until the bridge restarts, so this can describe
 * something that is no longer happening. That is deliberate: a power dip
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
