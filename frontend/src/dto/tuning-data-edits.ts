import type { Speaker, TuningDataDto } from "./profile.dto.ts";

const EQUALIZER_BAND_COUNT = 13;

/**
 * Names the equalizer slot the backend sends to the unit. A profile in LR mode
 * keeps one combined slot, `LR`. The backend's `selected_band_gains_db` picks
 * the slot the same way.
 *
 * The editor does not touch `expandEq`. The Pioneer app neither reads nor
 * writes it, and the backend does not send it.
 */
function equalizerSlotName(tuningData: TuningDataDto): string | undefined {
  const slotNames = Object.keys(tuningData.foundationEq.eqs);
  return slotNames.includes("LR") ? "LR" : slotNames[0];
}

/** Returns a copy of `tuningData` with one band of the selected bank changed. */
export function withEqualizerGain(
  tuningData: TuningDataDto,
  band: number,
  gain: number,
): TuningDataDto {
  const gains = equalizerGains(tuningData).map((value, index) => (index === band ? gain : value));
  return withEqualizerGains(tuningData, gains);
}

/** Returns a copy of `tuningData` with the selected bank's gains replaced. */
export function withEqualizerGains(
  tuningData: TuningDataDto,
  gains: readonly number[],
): TuningDataDto {
  const slotName = equalizerSlotName(tuningData);
  if (slotName === undefined) {
    return tuningData;
  }
  const slot = tuningData.foundationEq.eqs[slotName];
  const banks = slot.banks.map((bankGains, bankIndex) =>
    bankIndex === slot.selectedBank ? [...gains] : bankGains,
  );

  return {
    ...tuningData,
    foundationEq: {
      ...tuningData.foundationEq,
      eqs: { ...tuningData.foundationEq.eqs, [slotName]: { ...slot, banks } },
    },
  };
}

/** Returns a copy of `tuningData` with one field of one speaker channel changed. */
export function withSpeakerField(
  tuningData: TuningDataDto,
  channel: string,
  field: keyof Speaker,
  value: Speaker[keyof Speaker],
): TuningDataDto {
  const speaker = tuningData.speakers[channel];
  return {
    ...tuningData,
    speakers: {
      ...tuningData.speakers,
      [channel]: { ...speaker, [field]: value },
    },
  };
}

/** Reads the selected bank's 13 gains, or a flat curve if the profile has none. */
export function equalizerGains(tuningData: TuningDataDto): number[] {
  const slotName = equalizerSlotName(tuningData);
  const slot = slotName === undefined ? undefined : tuningData.foundationEq.eqs[slotName];
  return slot?.banks[slot.selectedBank] ?? new Array(EQUALIZER_BAND_COUNT).fill(0);
}
