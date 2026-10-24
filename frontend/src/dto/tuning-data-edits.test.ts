import { describe, expect, it } from "vitest";
import {
  equalizerGains,
  withEqualizerGain,
  withEqualizerGains,
  withSpeakerField,
} from "./tuning-data-edits.ts";
import { sampleTuningData } from "./testing/sample-profile.ts";

describe("withEqualizerGain", () => {
  it("replaces one band's gain and leaves the others untouched", () => {
    const original = sampleTuningData();

    const updated = withEqualizerGain(original, 3, 6.5);

    expect(equalizerGains(updated)[3]).toBe(6.5);
    expect(equalizerGains(updated).filter((_, index) => index !== 3)).toEqual(
      equalizerGains(original).filter((_, index) => index !== 3),
    );
  });

  it("does not mutate the original tuning data", () => {
    const original = sampleTuningData();
    withEqualizerGain(original, 0, 12);

    expect(equalizerGains(original)[0]).toBe(0);
  });

  it("edits only the bank the profile selects, because the backend sends that one", () => {
    const original = sampleTuningData();
    original.foundationEq.eqs.LR.selectedBank = 1;

    const updated = withEqualizerGain(original, 4, -3);

    expect(updated.foundationEq.eqs.LR.banks[1][4]).toBe(-3);
    expect(updated.foundationEq.eqs.LR.banks[0]).toEqual(original.foundationEq.eqs.LR.banks[0]);
  });

  it("leaves expandEq alone, because nothing sends it", () => {
    const original = sampleTuningData();

    const updated = withEqualizerGain(original, 2, 5);

    expect(updated.foundationEq.expandEq).toEqual(original.foundationEq.expandEq);
  });
});

describe("withEqualizerGains", () => {
  it("replaces the selected bank's whole curve, for an undo", () => {
    const original = sampleTuningData();
    original.foundationEq.eqs.LR.selectedBank = 1;
    const curve = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 0];

    const updated = withEqualizerGains(original, curve);

    expect(equalizerGains(updated)).toEqual(curve);
    expect(updated.foundationEq.eqs.LR.banks[0]).toEqual(original.foundationEq.eqs.LR.banks[0]);
  });
});

describe("withSpeakerField", () => {
  it("replaces one field on one speaker channel", () => {
    const original = sampleTuningData();

    const updated = withSpeakerField(original, "FL", "levelDB", 2.5);

    expect(updated.speakers.FL.levelDB).toBe(2.5);
    expect(updated.speakers.FR).toEqual(original.speakers.FR);
  });
});

describe("equalizerGains", () => {
  it("reads the selected bank's gain curve", () => {
    const tuningData = sampleTuningData();
    expect(equalizerGains(tuningData)).toHaveLength(13);
  });

  it("falls back to the first slot when the profile has no LR slot", () => {
    const tuningData = sampleTuningData();
    const slot = tuningData.foundationEq.eqs.LR;
    tuningData.foundationEq.eqs = { FRONT: { ...slot, banks: [new Array(13).fill(2), slot.banks[1]] } };

    expect(equalizerGains(tuningData)).toEqual(new Array(13).fill(2));
  });
});
