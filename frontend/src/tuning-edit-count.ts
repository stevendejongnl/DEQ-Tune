import type { Speaker, TuningDataDto } from "./dto/profile.dto.ts";
import { equalizerGains } from "./dto/tuning-data-edits.ts";

const SPEAKER_FIELDS: readonly (keyof Speaker)[] = [
  "levelDB",
  "timeAlignmentCm",
  "isPositivePhase",
];

/** How many bands and speaker fields differ between the draft and the
 * factory data. The badge above the panels counts these. */
export function countEdits(draft: TuningDataDto, factory: TuningDataDto): number {
  return countBandEdits(draft, factory) + countSpeakerEdits(draft, factory);
}

export function countBandEdits(draft: TuningDataDto, factory: TuningDataDto): number {
  const draftGains = equalizerGains(draft);
  const factoryGains = equalizerGains(factory);
  return draftGains.filter((gain, band) => gain !== factoryGains[band]).length;
}

function countSpeakerEdits(draft: TuningDataDto, factory: TuningDataDto): number {
  let edits = 0;
  for (const [channel, speaker] of Object.entries(draft.speakers)) {
    const factorySpeaker = factory.speakers[channel];
    if (factorySpeaker === undefined) {
      continue;
    }
    for (const field of SPEAKER_FIELDS) {
      if (speaker[field] !== factorySpeaker[field]) {
        edits += 1;
      }
    }
  }
  return edits;
}
