import type { Locale } from "./locale.ts";
import english from "./locales/en.json";
import japanese from "./locales/ja.json";
import german from "./locales/de.json";
import french from "./locales/fr.json";
import spanish from "./locales/es.json";
import dutch from "./locales/nl.json";

export type UiStrings = {
  factoryPresets: string;
  myProfiles: string;
  duplicate: string;
  delete: string;
  duplicateHint: string;
  selectProfilePrompt: string;
  speakers: string;
  speakerColumn: string;
  levelColumn: string;
  timeAlignmentColumn: string;
  phaseColumn: string;
  speakerFrontLeft: string;
  speakerFrontRight: string;
  speakerRearLeft: string;
  speakerRearRight: string;
  languageLabel: string;
  eqStyleTitle: string;
  liveSimulationTitle: string;
  dspDeviceHint: string;
  profilesButton: string;
  closeLabel: string;
  tabEq: string;
  tabStyle: string;
  frequencyResponseTitle: string;
  legendYours: string;
  legendFactory: string;
  zoneNameSubBass: string;
  zoneNameBass: string;
  zoneNameLowMids: string;
  zoneNameMids: string;
  zoneNamePresence: string;
  zoneNameAir: string;
  zoneHintSubBass: string;
  zoneHintBass: string;
  zoneHintLowMids: string;
  zoneHintMids: string;
  zoneHintPresence: string;
  zoneHintAir: string;
  factoryValuePrefix: string;
  resetBand: string;
  gainSliderLabel: string;
  lowerGainLabel: string;
  raiseGainLabel: string;
  speakersTitle: string;
  cabinHintPick: string;
  cabinHintTap: string;
  listenerLabel: string;
  levelLabel: string;
  delayLabel: string;
  phaseLabel: string;
  phaseNormal: string;
  phaseInverted: string;
  lowerLevelLabel: string;
  raiseLevelLabel: string;
  shorterDelayLabel: string;
  longerDelayLabel: string;
  soundStyleTitle: string;
  soundStyleSuffix: string;
  findYourCar: string;
  customProfileCaption: string;
  speakerPioneerShort: string;
  speakerStockShort: string;
  factoryGroupLabel: string;
  moreActionsLabel: string;
  deviceNotConnected: string;
  deviceConnected: string;
  bridgeUnreachable: string;
  dismiss: string;
  bridgeNoticeDismissHint: string;
  factoryBadge: string;
  editedBadgeOne: string;
  editedBadgeMany: string;
  revertToFactory: string;
  saveAsMyProfile: string;
  revertShort: string;
  saveShort: string;
  startEditingHint: string;
  discardDraftConfirm: string;
  newProfile: string;
  newProfileName: string;
  saveUnitTune: string;
  unitTuneName: string;
  rename: string;
  renameLabel: string;
  audioTitle: string;
  audioNotRead: string;
  audioNotConnected: string;
  audioSourceLabel: string;
  audioVolumeLabel: string;
  audioMutedLabel: string;
  audioMutedYes: string;
  audioMutedNo: string;
  audioMutedUnknown: string;
  audioDrivingLabel: string;
  audioDrivingYes: string;
  audioDrivingNo: string;
  audioSourceStandAlone: string;
  audioSourceCarSource: string;
  audioSourceThrough: string;
};

/** The source catalog. Every key the app reads must be here, so the compiler
 * checks this one file against UiStrings. */
const ENGLISH: UiStrings = english;

/** A translation holds only what a translator finished. Weblate writes the
 * file that way, so each one is partial by contract. */
const TRANSLATIONS: Record<Locale, Partial<UiStrings>> = {
  en: english,
  ja: japanese,
  de: german,
  fr: french,
  es: spanish,
  nl: dutch,
};

function isTranslated(value: unknown): value is string {
  return typeof value === "string" && value.trim() !== "";
}

/** English for every key, with each translated value on top. A key the
 * translator has not reached yet reads English, never undefined. */
export function mergeOverEnglish(source: UiStrings, translation: Partial<UiStrings>): UiStrings {
  const merged: Record<string, string> = { ...source };
  for (const [key, value] of Object.entries(translation)) {
    if (isTranslated(value)) {
      merged[key] = value;
    }
  }
  // Safe: the loop only writes keys that source already holds.
  return merged as UiStrings;
}

const UI_STRINGS: Record<Locale, UiStrings> = {
  en: ENGLISH,
  ja: mergeOverEnglish(ENGLISH, TRANSLATIONS.ja),
  de: mergeOverEnglish(ENGLISH, TRANSLATIONS.de),
  fr: mergeOverEnglish(ENGLISH, TRANSLATIONS.fr),
  es: mergeOverEnglish(ENGLISH, TRANSLATIONS.es),
  nl: mergeOverEnglish(ENGLISH, TRANSLATIONS.nl),
};

export function uiStrings(locale: Locale): UiStrings {
  return UI_STRINGS[locale];
}
