import { describe, expect, it } from "vitest";
import { equalizerName } from "./equalizer-names.ts";
import type { EqualizerDto } from "../dto/profile.dto.ts";
import { eqStyleName } from "./dsp-presets.ts";

function equalizer(name: string, source: "factory" | "custom"): EqualizerDto {
  return { id: 1, name, source, gains: new Array(13).fill(0) };
}

describe("equalizerName", () => {
  it("shows a factory EQ under Pioneer's own name for the locale", () => {
    expect(equalizerName(equalizer("Super Bass", "factory"), "en")).toBe("Super Bass");
    expect(equalizerName(equalizer("Super Bass", "factory"), "ja")).toBe(
      eqStyleName("ja", "SUPER_BASS"),
    );
  });

  it("keeps the typed name of a custom EQ, even when it matches a style", () => {
    expect(equalizerName(equalizer("Super Bass", "custom"), "ja")).toBe("Super Bass");
  });

  it("keeps the name of a factory EQ it does not know", () => {
    expect(equalizerName(equalizer("Night drive", "factory"), "en")).toBe("Night drive");
  });
});
