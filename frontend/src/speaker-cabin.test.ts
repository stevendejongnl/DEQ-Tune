import { describe, expect, it } from "vitest";
import { listenerSide, speakerButtonSize } from "./speaker-cabin.ts";
import type { Speaker } from "./dto/profile.dto.ts";

function speaker(timeAlignmentCm: number): Speaker {
  return { isPositivePhase: true, levelDB: 0, timeAlignmentCm, levelDBExtended: 0 };
}

describe("listenerSide", () => {
  it("seats the listener on the side whose speakers are nearer", () => {
    // The Dacia's estimates: the left speakers are the near ones.
    const duster = { FL: speaker(85), FR: speaker(133), RL: speaker(96), RR: speaker(141) };
    expect(listenerSide(duster)).toBe("left");
  });

  it("seats the listener on the right in a Japanese Mazda preset", () => {
    const mazdaFactory = {
      FL: speaker(130),
      FR: speaker(95),
      RL: speaker(117.5),
      RR: speaker(67.5),
    };
    expect(listenerSide(mazdaFactory)).toBe("right");
  });

  it("seats the listener on the left when every distance is the same", () => {
    const flat = { FL: speaker(0), FR: speaker(0), RL: speaker(0), RR: speaker(0) };
    expect(listenerSide(flat)).toBe("left");
  });

  it("falls back to the left when there are no speakers", () => {
    expect(listenerSide({})).toBe("left");
  });
});

describe("speakerButtonSize", () => {
  it("grows the button with the level", () => {
    expect(speakerButtonSize(0, false)).toBe(40);
    expect(speakerButtonSize(4, false)).toBe(48);
    expect(speakerButtonSize(-4, false)).toBe(32);
  });

  it("keeps touch targets at 44 px or more", () => {
    expect(speakerButtonSize(-4, true)).toBe(44);
    expect(speakerButtonSize(6, true)).toBe(52);
  });
});
