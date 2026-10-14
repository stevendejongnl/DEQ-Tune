import { describe, expect, it } from "vitest";
import { countBandEdits, countEdits } from "./tuning-edit-count.ts";
import { sampleTuningData } from "./dto/testing/sample-profile.ts";
import { withEqualizerGain, withSpeakerField } from "./dto/tuning-data-edits.ts";

describe("countEdits", () => {
  it("counts nothing for untouched data", () => {
    const factory = sampleTuningData();
    expect(countEdits(factory, factory)).toBe(0);
  });

  it("counts every band that differs", () => {
    const factory = sampleTuningData();
    let draft = withEqualizerGain(factory, 0, 3);
    draft = withEqualizerGain(draft, 5, -2);

    expect(countBandEdits(draft, factory)).toBe(2);
  });

  it("counts a changed speaker field", () => {
    const factory = sampleTuningData();
    const draft = withSpeakerField(factory, "FL", "levelDB", 2);

    expect(countEdits(draft, factory)).toBe(1);
  });

  it("adds band edits and speaker edits together", () => {
    const factory = sampleTuningData();
    let draft = withEqualizerGain(factory, 3, 6);
    draft = withSpeakerField(draft, "RR", "isPositivePhase", false);
    draft = withSpeakerField(draft, "RR", "timeAlignmentCm", 40);

    expect(countEdits(draft, factory)).toBe(3);
  });
});
