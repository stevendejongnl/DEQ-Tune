import type { ProfileDto, Speaker, TuningDataDto } from "../profile.dto.ts";

const ZERO_BAND = new Array(13).fill(0);
const BAND_FREQUENCIES = [50, 80, 125, 200, 315, 500, 800, 1250, 2000, 3150, 5000, 8000, 12500];

function sampleSpeaker(): Speaker {
  return { isPositivePhase: true, levelDB: 0, timeAlignmentCm: 0, levelDBExtended: 0 };
}

/** A minimal but schema-valid TuningDataDto: all bands flat, all speakers neutral. */
export function sampleTuningData(): TuningDataDto {
  return {
    foundationEq: {
      isLRMode: false,
      eqs: { LR: { isLocked: true, numOfBand: 13, selectedBank: 0, banks: [ZERO_BAND, ZERO_BAND] } },
      expandEq: {
        FRONT: {
          isLocked: true,
          numOfBand: 13,
          selectedBank: 0,
          banks: { q: ZERO_BAND.map(() => 4.7), f0: BAND_FREQUENCIES, gain: ZERO_BAND },
        },
      },
    },
    speakers: { FL: sampleSpeaker(), FR: sampleSpeaker(), RL: sampleSpeaker(), RR: sampleSpeaker() },
    filter: {
      front: { cutoff_hpf: 0, slope_hpf: 0 },
      rear: { cutoff_hpf: 0, slope_hpf: 0 },
    },
    factoryCancel: {
      available: false,
      enabled: false,
      data: { cancellingEQ: { L: ZERO_BAND, R: ZERO_BAND }, cancellingTACm: { L: 0, R: 0 } },
    },
    faderBalance: { fader: 0, balance: 0 },
    timeAlignment: { enabled: true, easySoundFitModeEnabled: false, easySoundFitMode: -1 },
  };
}

/** A schema-valid ProfileDto fixture. Pass `overrides` for the fields a test cares about. */
export function sampleProfile(overrides: Partial<ProfileDto> = {}): ProfileDto {
  return {
    id: 1,
    name: "Sample profile",
    source: "factory",
    brand_name: "Mazda",
    car_model: "mazda_3",
    speaker_type: "general",
    supported_processors: ["DEQ-1000A-MZ"],
    favorite: false,
    data: sampleTuningData(),
    ...overrides,
  };
}
