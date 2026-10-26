import { ApiError, type CrossoverApi } from "../../api/client.ts";
import type { CrossoverDto, CrossoverFilterWriteDto, SpeakerModeWriteDto } from "../../dto/profile.dto.ts";

const LOW_CUTOFFS_HZ = [25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250];

/** The car's crossover: speaker mode 3, with the subwoofer at 50 Hz and
 * 24 dB per octave, as the unit held it on 2026-10-08. */
export function carCrossover(): CrossoverDto {
  return {
    speaker_mode: "STANDARD_FL_FR_RL_RR_SW",
    speaker_modes: [
      "STANDARD_FL_FR",
      "STANDARD_FL_FR_RL_RR",
      "STANDARD_FL_FR_RL_RR_SW",
      "STANDARD_FL_FR_RLSW_RRSW",
      "STANDARD_FL_FR_SW",
    ],
    filters: [
      { speaker: "front", kind: "high_pass", owner: "profile", cutoff_position: 6, slope: 0, cutoffs_hz: LOW_CUTOFFS_HZ },
      { speaker: "rear", kind: "high_pass", owner: "profile", cutoff_position: 9, slope: 2, cutoffs_hz: LOW_CUTOFFS_HZ },
      { speaker: "subwoofer", kind: "low_pass", owner: "unit", cutoff_position: 3, slope: 4, cutoffs_hz: LOW_CUTOFFS_HZ },
    ],
  };
}

/** The stored filters each STANDARD mode uses, as `unit_crossover.py` maps
 * them. The rear-subwoofer mode is left out: the car fixture has no such
 * filter. */
const SPEAKERS_BY_MODE: Record<string, string[]> = {
  STANDARD_FL_FR: ["front"],
  STANDARD_FL_FR_RL_RR: ["front", "rear"],
  STANDARD_FL_FR_RL_RR_SW: ["front", "rear", "subwoofer"],
  STANDARD_FL_FR_RLSW_RRSW: ["front"],
  STANDARD_FL_FR_SW: ["front", "subwoofer"],
};

/** A unit's crossover in memory. It stores each write, the way the
 * backend answers with what the unit holds after the change. */
export class FakeCrossoverApi implements CrossoverApi {
  crossover: CrossoverDto;
  writes: CrossoverFilterWriteDto[] = [];
  modeChanges: string[] = [];
  /** The status a read or write fails with, or null to answer. */
  failWith: number | null = null;

  constructor(crossover: CrossoverDto = carCrossover()) {
    this.crossover = crossover;
  }

  async readCrossover(): Promise<CrossoverDto> {
    this.failIfAsked("GET");
    return structuredClone(this.crossover);
  }

  async writeCrossoverFilter(body: CrossoverFilterWriteDto): Promise<CrossoverDto> {
    this.failIfAsked("PUT");
    this.writes.push(body);
    const filter = this.crossover.filters.find((one) => one.speaker === body.speaker)!;
    filter.cutoff_position = body.cutoff_position;
    filter.slope = body.slope;
    return structuredClone(this.crossover);
  }

  /** Moves to a mode, and keeps only the filters it uses: the front and
   * rear filters for front-and-rear modes, the subwoofer's with one. */
  async changeSpeakerMode(body: SpeakerModeWriteDto): Promise<CrossoverDto> {
    this.failIfAsked("PUT");
    this.modeChanges.push(body.speaker_mode);
    const all = carCrossover().filters;
    const speakers = SPEAKERS_BY_MODE[body.speaker_mode];
    this.crossover = {
      ...this.crossover,
      speaker_mode: body.speaker_mode,
      filters: all.filter((filter) => speakers.includes(filter.speaker)),
    };
    return structuredClone(this.crossover);
  }

  private failIfAsked(method: string): void {
    if (this.failWith !== null) {
      throw new ApiError(this.failWith, `${method} /device/crossover failed: ${this.failWith}`);
    }
  }
}
