import type { Locale } from "./locale.ts";

/**
 * Names for the DEQ device's built-in EQ-style and Live-Simulation DSP
 * presets. The ids are the device's own enum names
 * (`backend/app/deq_enums.json`'s `eq_style`/`live_simulation`), not an
 * invented local id, so there is no separate id-to-wire-name map to keep
 * in sync with the device.
 *
 * Names come from the Pioneer app's own string resources where one
 * exists. A handful of newer enum members (see NO_STRING_RESOURCE below)
 * have no resource in any locale of the decompiled APK at all, not even
 * English. Their name here is a plain title-cased fallback, not a
 * translation of anything Pioneer shipped.
 *
 * Selecting one of these only takes effect on a connected device (see
 * dsp-panel.ts). There's no local curve data for them to preview. The DSP
 * itself lives in the device's firmware.
 */

export const EQ_STYLE_IDS = [
  "CUSTOM",
  "FLAT",
  "SUPER_BASS",
  "POWERFUL",
  "NATURAL",
  "VOCAL",
  "TODOROKI",
  "POP_ROCK",
  "ELETRONICA",
  "SAMBA",
  "SERTANEJO",
  "PRO",
  "BANDA",
  "DYNAMIC",
  "FORRO",
  "VIVID",
  "JAZZ",
  "ULTRA_BASS",
  "TRUE_ACOUSTIC",
  "EDM_BEAST",
] as const;
export type EqStyleId = (typeof EQ_STYLE_IDS)[number];

export const LIVE_SIMULATION_IDS = [
  "OFF",
  "CONCERT_HALL",
  "OPEN_AIR",
  "CLUB",
  "CAFE",
  "OPERA_HALL",
  "DJ_DANCE_PARTY",
] as const;
export type LiveSimulationId = (typeof LIVE_SIMULATION_IDS)[number];

/**
 * Enum members with no string resource in any locale of the decompiled
 * APK, English included. A search of every values-\* strings.xml for each
 * one confirmed this. They are newer additions to the device's enum that
 * Pioneer has not yet given a string resource. This file names them with a
 * plain title-cased fallback rather than leaving them blank.
 */
const NO_STRING_RESOURCE_EQ_STYLES: ReadonlySet<EqStyleId> = new Set([
  "ULTRA_BASS",
  "TRUE_ACOUSTIC",
  "EDM_BEAST",
]);
const NO_STRING_RESOURCE_LIVE_SIMULATIONS: ReadonlySet<LiveSimulationId> = new Set([
  "OPERA_HALL",
  "DJ_DANCE_PARTY",
]);

const ENGLISH_EQ_STYLE_NAMES: Record<EqStyleId, string> = {
  CUSTOM: "Custom",
  FLAT: "FLAT",
  SUPER_BASS: "Super Bass",
  POWERFUL: "Powerful",
  NATURAL: "Natural",
  VOCAL: "Vocal",
  TODOROKI: "TODOROKI",
  POP_ROCK: "Pop rock",
  ELETRONICA: "Eletrônica",
  SAMBA: "Samba",
  SERTANEJO: "Sertanejo",
  PRO: "P.R.O.",
  BANDA: "BANDA",
  DYNAMIC: "Dynamic",
  FORRO: "Forró",
  VIVID: "Vivid",
  JAZZ: "Jazz",
  ULTRA_BASS: "Ultra Bass",
  TRUE_ACOUSTIC: "True Acoustic",
  EDM_BEAST: "EDM Beast",
};

/**
 * A locale without an entry for a given id shows the English name. Most
 * of these ids only ever shipped with one Pioneer translation (often the
 * English text reused word for word). So most locales below are sparse on
 * purpose. The APK's own strings.xml files have the same gaps. They are
 * not a gap in this app's translation.
 */
const EQ_STYLE_NAMES: Partial<Record<Locale, Partial<Record<EqStyleId, string>>>> = {
  en: ENGLISH_EQ_STYLE_NAMES,
  ja: {
    SUPER_BASS: "SUPER BASS",
    POWERFUL: "POWERFUL",
    NATURAL: "NATURAL",
    VOCAL: "VOCAL",
    VIVID: "Vivid",
    DYNAMIC: "Dynamic",
    FLAT: "FLAT",
    TODOROKI: "TODOROKI",
    BANDA: "BANDA",
  },
  de: {
    SUPER_BASS: "SUPERBASS",
    POWERFUL: "KRAFTVOLL",
    NATURAL: "NATÜRLICH",
    VOCAL: "VOKAL",
    VIVID: "Lebhaft",
    DYNAMIC: "Dynamisch",
    FLAT: "FLACH",
    TODOROKI: "TODOROKI",
    POP_ROCK: "Pop-Rock",
    BANDA: "BANDA",
  },
  fr: {
    SUPER_BASS: "SUPER BASS",
    POWERFUL: "POWERFUL",
    NATURAL: "NATURAL",
    VOCAL: "VOCAL",
    VIVID: "Viv",
    DYNAMIC: "Dynamiq",
    FLAT: "FLAT",
    TODOROKI: "TODOROKI",
    BANDA: "BANDA",
  },
  es: {
    SUPER_BASS: "SUPERGRAV",
    POWERFUL: "POTENTE",
    NATURAL: "NATURAL",
    VOCAL: "VOCAL",
    VIVID: "Vívid",
    DYNAMIC: "Dinám.",
    FLAT: "NORM",
    TODOROKI: "TODOROKI",
    ELETRONICA: "Electrón.",
    BANDA: "BANDA",
  },
  nl: {
    SUPER_BASS: "SUPERBASS",
    POWERFUL: "KRACHTIG",
    NATURAL: "NATUUR",
    VOCAL: "VOCAAL",
    VIVID: "Levendig",
    DYNAMIC: "Dynamisch",
    FLAT: "VLAK",
    TODOROKI: "TODOROKI",
    POP_ROCK: "Pop-rock",
    BANDA: "BANDA",
  },
};

const ENGLISH_LIVE_SIMULATION_NAMES: Record<LiveSimulationId, string> = {
  OFF: "OFF",
  CONCERT_HALL: "Concert hall",
  OPEN_AIR: "Open air",
  CLUB: "Club",
  CAFE: "Cafe",
  OPERA_HALL: "Opera Hall",
  DJ_DANCE_PARTY: "DJ Dance Party",
};

/**
 * OPERA_HALL and DJ_DANCE_PARTY have no entry anywhere (see
 * NO_STRING_RESOURCE_LIVE_SIMULATIONS above). So every locale below leaves
 * out those two on purpose.
 */
const LIVE_SIMULATION_NAMES: Partial<Record<Locale, Partial<Record<LiveSimulationId, string>>>> =
  {
    en: ENGLISH_LIVE_SIMULATION_NAMES,
    ja: { OFF: "OFF", CONCERT_HALL: "ドーム", OPEN_AIR: "野外フェス", CLUB: "ライブハウス", CAFE: "ミュージックバー" },
    de: { OFF: "AUS", CONCERT_HALL: "Konzerthalle", OPEN_AIR: "Freiluft", CLUB: "Club", CAFE: "Café" },
    fr: { OFF: "ARR", CONCERT_HALL: "Salle concer", OPEN_AIR: "Extér", CLUB: "Club", CAFE: "Café" },
    es: { OFF: "OFF", CONCERT_HALL: "Sala conc.", OPEN_AIR: "Aire", CLUB: "Club", CAFE: "Café" },
    nl: { OFF: "UIT", CONCERT_HALL: "Concertzaal", OPEN_AIR: "Openlucht", CLUB: "Club", CAFE: "Café" },
  };

export function eqStyleName(locale: Locale, id: EqStyleId): string {
  return EQ_STYLE_NAMES[locale]?.[id] ?? ENGLISH_EQ_STYLE_NAMES[id];
}

export function liveSimulationName(locale: Locale, id: LiveSimulationId): string {
  return LIVE_SIMULATION_NAMES[locale]?.[id] ?? ENGLISH_LIVE_SIMULATION_NAMES[id];
}

export function eqStyleHasNoPioneerTranslation(id: EqStyleId): boolean {
  return NO_STRING_RESOURCE_EQ_STYLES.has(id);
}

export function liveSimulationHasNoPioneerTranslation(id: LiveSimulationId): boolean {
  return NO_STRING_RESOURCE_LIVE_SIMULATIONS.has(id);
}
