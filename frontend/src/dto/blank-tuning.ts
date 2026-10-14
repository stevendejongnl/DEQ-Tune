import type { Speaker, TuningDataDto } from "./profile.dto.ts";

const EQUALIZER_BAND_COUNT = 13;
const PROFILE_CHANNELS = ["FL", "FR", "RL", "RR"] as const;

function flatBank(): number[] {
  return new Array(EQUALIZER_BAND_COUNT).fill(0);
}

function neutralSpeaker(): Speaker {
  return { isPositivePhase: true, levelDB: 0, timeAlignmentCm: 0, levelDBExtended: 0 };
}

/**
 * Returns the tuning of a new profile: a flat curve in both banks, every
 * speaker at 0 dB with no delay, no high-pass filter, and no factory
 * cancelling. A new profile starts from nothing. A copy of a preset comes
 * from "Save as my profile" or Duplicate instead.
 */
export function blankTuningData(): TuningDataDto {
  return {
    foundationEq: {
      isLRMode: false,
      eqs: {
        LR: {
          isLocked: false,
          numOfBand: EQUALIZER_BAND_COUNT,
          selectedBank: 0,
          banks: [flatBank(), flatBank()],
        },
      },
      expandEq: {},
    },
    speakers: Object.fromEntries(PROFILE_CHANNELS.map((channel) => [channel, neutralSpeaker()])),
    filter: {
      front: { cutoff_hpf: 0, slope_hpf: 0 },
      rear: { cutoff_hpf: 0, slope_hpf: 0 },
    },
    factoryCancel: {
      available: false,
      enabled: false,
      data: { cancellingEQ: { L: flatBank(), R: flatBank() }, cancellingTACm: { L: 0, R: 0 } },
    },
    faderBalance: { fader: 0, balance: 0 },
    timeAlignment: { enabled: true, easySoundFitModeEnabled: false, easySoundFitMode: -1 },
  };
}
