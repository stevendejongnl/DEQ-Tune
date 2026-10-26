import type { Locale } from "./locale.ts";
import english from "./locales/en.json";
import japanese from "./locales/ja.json";
import german from "./locales/de.json";
import french from "./locales/fr.json";
import spanish from "./locales/es.json";
import dutch from "./locales/nl.json";

export type UiStrings = {
  communityShareGuide: string;
  communityShareFailed: string;
  communityShareNothing: string;
  communityShareItem: string;
  communityShareEqualizers: string;
  communityShareProfiles: string;
  communityShareAuthor: string;
  communityShareDescription: string;
  communityShareDescriptionHint: string;
  communityShareBrand: string;
  communityShareModel: string;
  communityShareInvalid: string;
  communityShareMake: string;
  communityShareStepsPrefilled: string;
  communityShareStepsPaste: string;
  communityShareOpenGithub: string;
  communityShareCopy: string;
  communityShareCopied: string;
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
  library: string;
  libraryBack: string;
  favorites: string;
  favoritesHint: string;
  addFavoriteLabel: string;
  removeFavoriteLabel: string;
  activate: string;
  activeApplied: string;
  activeWaiting: string;
  activeOutdated: string;
  activeFailed: string;
  applyChanges: string;
  tryAgain: string;
  saveBeforeActivate: string;
  activeTag: string;
  noEqualizer: string;
  equalizerNameLabel: string;
  deleteEqualizer: string;
  newEqualizerName: string;
  carCorrectionTitle: string;
  backLabel: string;
  pageSound: string;
  pageCar: string;
  noEqualizerHint: string;
  factoryEqualizerHint: string;
  rename: string;
  renameLabel: string;
  audioTitle: string;
  audioNotRead: string;
  audioNotConnected: string;
  audioBridgeUnreachable: string;
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
  wifiTitle: string;
  wifiOpenLabel: string;
  wifiIntro: string;
  wifiSavedTitle: string;
  wifiNoneSaved: string;
  wifiConnected: string;
  wifiForget: string;
  wifiForgetConnectedConfirm: string;
  wifiAddTitle: string;
  wifiSsidLabel: string;
  wifiPasswordLabel: string;
  wifiPasswordHint: string;
  wifiSave: string;
  wifiSaved: string;
  wifiJoinNow: string;
  wifiJoinRequested: string;
  wifiInRange: string;
  wifiUnavailable: string;
  wifiRefused: string;
  wifiInvalid: string;
  wifiFailed: string;
  backupIntro: string;
  backupExport: string;
  backupImport: string;
  backupExported: string;
  backupNotSaved: string;
  undoEqualizerEdit: string;
  settingsLanguageAndroid: string;
  settingsTranslationsTitle: string;
  settingsTranslationsText: string;
  settingsTranslateLink: string;
  settingsTranslatingGuideLink: string;
  pageChecking: string;
  audioVolumeDown: string;
  audioVolumeUp: string;
  systemUnitSection: string;
  systemUnitFirmware: string;
  settingsSectionCommunity: string;
  settingsSectionBluetooth: string;
  bluetoothIntro: string;
  bluetoothOpenUntil: string;
  bluetoothClosed: string;
  bluetoothPairNew: string;
  bluetoothPairFailed: string;
  bluetoothPairAtCarStart: string;
  bluetoothPairAtCarStartHint: string;
  bluetoothPairedPhones: string;
  bluetoothNoPhones: string;
  bluetoothUnsupported: string;
  bluetoothFailed: string;
  communityIntro: string;
  communityLoading: string;
  communityLoadFailed: string;
  communityRetry: string;
  communityFilterAll: string;
  communityFilterEqualizers: string;
  communityFilterProfiles: string;
  communitySearch: string;
  communityEmpty: string;
  communityKindEqualizer: string;
  communityKindProfile: string;
  communityBy: string;
  communityProfileWarning: string;
  communityAdd: string;
  communityAdded: string;
  communityPresent: string;
  communityContribute: string;
  backupImported: string;
  backupNotALibrary: string;
  backupFailed: string;
  settingsSectionBackup: string;
  settingsSectionPhone: string;
  phoneModeTitle: string;
  phoneModeAutomatic: string;
  phoneModeAutomaticHint: string;
  phoneModeBluetooth: string;
  phoneModeBluetoothHint: string;
  phoneModeAccessPoint: string;
  phoneModeAccessPointHint: string;
  phoneConnectedWifi: string;
  phoneConnectedBluetooth: string;
  phoneConnectedBluetoothOnly: string;
  phoneConnectedAccessPoint: string;
  phoneSearching: string;
  phoneSearchAgain: string;
  phonePermissionsMissing: string;
  phoneAllow: string;
  phoneAccessPointUrl: string;
  phonePasswordSaved: string;
  phoneSaved: string;
  phoneAppVersion: string;
  accessPointTitle: string;
  accessPointIntro: string;
  accessPointDefaultKey: string;
  accessPointOwnKey: string;
  accessPointKeyLabel: string;
  accessPointKeyHint: string;
  accessPointRepeatLabel: string;
  accessPointSave: string;
  accessPointSaved: string;
  accessPointSetupTitle: string;
  accessPointSetupIntro: string;
  accessPointSetupLater: string;
  accessPointSetupDone: string;
  accessPointNoticeTitle: string;
  accessPointNoticeAction: string;
  pageLive: string;
  pageOffline: string;
  pageOutdated: string;
  systemOpenLabel: string;
  systemTitle: string;
  settingsTitle: string;
  settingsOpenLabel: string;
  settingsBack: string;
  settingsSectionUpdates: string;
  settingsSectionWifi: string;
  settingsSectionSystem: string;
  settingsSectionLanguage: string;
  settingsLanguageHint: string;
  updatesIntro: string;
  updatesInstalled: string;
  updatesLatest: string;
  updatesChecked: string;
  updatesLastResult: string;
  updatesAutomatic: string;
  updatesAutomaticHint: string;
  updatesCheckNow: string;
  updatesRequested: string;
  updatesUnsupported: string;
  updatesFailed: string;
  updatesChangelog: string;
  updatesGadgetPending: string;
  updatesHistory: string;
  updatesNever: string;
  whatsNewTitle: string;
  whatsNewDismiss: string;
  updateAvailableTitle: string;
  updateAvailableInstall: string;
  updateAvailableLater: string;
  systemUnreachable: string;
  systemPageSection: string;
  systemPageState: string;
  systemPageBuild: string;
  systemServedBuild: string;
  systemOutdatedHint: string;
  systemReload: string;
  systemMachineSection: string;
  systemHostname: string;
  systemModel: string;
  systemOperatingSystem: string;
  systemKernel: string;
  systemPython: string;
  systemUptime: string;
  systemLoad: string;
  systemCpu: string;
  systemTemperature: string;
  systemThrottled: string;
  systemMemorySection: string;
  systemRam: string;
  systemSwap: string;
  systemBackendMemory: string;
  systemDisk: string;
  systemNetworkSection: string;
  systemNoInterfaces: string;
  systemCores: string;
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
