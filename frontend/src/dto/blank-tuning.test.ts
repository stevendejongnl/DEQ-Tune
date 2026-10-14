import typia from "typia";
import { describe, expect, it } from "vitest";
import { blankTuningData } from "./blank-tuning.ts";
import { equalizerGains } from "./tuning-data-edits.ts";
import type { TuningDataDto } from "./profile.dto.ts";

describe("blankTuningData", () => {
  it("is a valid tuning the backend accepts", () => {
    expect(() => typia.assert<TuningDataDto>(blankTuningData())).not.toThrow();
  });

  it("starts flat, with neutral speakers", () => {
    const tuning = blankTuningData();

    expect(equalizerGains(tuning)).toEqual(new Array(13).fill(0));
    expect(Object.values(tuning.speakers).every((speaker) => speaker.levelDB === 0)).toBe(true);
    expect(tuning.factoryCancel.enabled).toBe(false);
  });

  it("hands out a new object each time, so one profile's edit stays its own", () => {
    const first = blankTuningData();
    first.foundationEq.eqs.LR.banks[0][0] = 6;

    expect(equalizerGains(blankTuningData())[0]).toBe(0);
  });
});
