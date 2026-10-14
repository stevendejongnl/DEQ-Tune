import type { EqualizerDto } from "../dto/profile.dto.ts";
import { eqStyleName, type EqStyleId } from "./dsp-presets.ts";
import type { Locale } from "./locale.ts";

/** The backend names a factory EQ after Pioneer's own style, in English.
 * This maps each name back to the style, so the app shows the name that
 * Pioneer translated for the locale. */
const FACTORY_STYLE_IDS: Record<string, EqStyleId> = {
  Flat: "FLAT",
  "Super Bass": "SUPER_BASS",
  Powerful: "POWERFUL",
  Natural: "NATURAL",
  Vocal: "VOCAL",
  TODOROKI: "TODOROKI",
  "Pop rock": "POP_ROCK",
  "Eletrônica": "ELETRONICA",
  Samba: "SAMBA",
  Sertanejo: "SERTANEJO",
  "P.R.O.": "PRO",
  Vivid: "VIVID",
  Dynamic: "DYNAMIC",
  BANDA: "BANDA",
};

/** Returns the name to show. A custom EQ keeps the name its owner typed. */
export function equalizerName(equalizer: EqualizerDto, locale: Locale): string {
  const styleId = equalizer.source === "factory" ? FACTORY_STYLE_IDS[equalizer.name] : undefined;
  return styleId === undefined ? equalizer.name : eqStyleName(locale, styleId);
}
