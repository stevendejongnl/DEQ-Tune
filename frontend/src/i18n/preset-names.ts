import type { Locale } from "./locale.ts";
import type { ProfileDto } from "../dto/profile.dto.ts";

/**
 * English and Japanese are the only locales with model/speaker-type
 * names that differ in the Pioneer app's own string resources.
 * German/French/Spanish ship the same English text there.
 * Locales without an entry here fall back to English.
 */
const MODEL_NAMES: Partial<Record<Locale, Record<string, string>>> = {
  en: {
    mazda_2: "Mazda2",
    mazda_3: "Mazda3",
    mazda_6: "Mazda6",
    mazda_cx3: "CX-3",
    mazda_cx5: "CX-5",
    mazda_cx8: "CX-8",
    mazda_mx5: "Mazda MX-5",
  },
  ja: {
    mazda_2: "DEMIO",
    mazda_3: "AXELA",
    mazda_6: "ATENZA",
    mazda_cx3: "CX-3",
    mazda_cx5: "CX-5",
    mazda_cx8: "CX-8",
    mazda_mx5: "ROADSTER",
  },
};

const SPEAKER_TYPE_LABELS: Partial<Record<Locale, Record<string, string>>> = {
  en: {
    general: "For Normal Speaker",
    carrozzeria: "For Pioneer Speaker",
  },
  ja: {
    general: "純正スピーカー用",
    carrozzeria: "カロッツェリアスピーカー用",
  },
};

function translateModelName(locale: Locale, carModel: string): string {
  return MODEL_NAMES[locale]?.[carModel] ?? MODEL_NAMES.en?.[carModel] ?? carModel;
}

function translateSpeakerType(locale: Locale, speakerType: string): string {
  return (
    SPEAKER_TYPE_LABELS[locale]?.[speakerType] ?? SPEAKER_TYPE_LABELS.en?.[speakerType] ?? speakerType
  );
}

/** A factory preset's car model in `locale`, for example "Mazda2", or
 * "DEMIO" in Japanese.
 *
 * Returns null for a custom profile, which shows the name the user
 * typed instead. A custom profile does carry a `car_model`: duplicating
 * a factory preset copies it, so the tuning keeps the car Pioneer made
 * it for. That field says which car the numbers suit. It is not the
 * profile's name, and showing it in place of the name hid every rename
 * a user made. */
export function localizedModelName(profile: ProfileDto, locale: Locale): string | null {
  if (profile.source !== "factory" || profile.car_model === null) {
    return null;
  }
  return translateModelName(locale, profile.car_model);
}

/** A factory preset's speaker type in `locale`, for example "For
 * Pioneer Speaker".
 *
 * Returns null for a custom profile, for the same reason as
 * `localizedModelName`: a duplicate copies `speaker_type`, and showing
 * it made a renamed profile keep the breadcrumb of the preset it came
 * from. */
export function localizedSpeakerTypeLabel(profile: ProfileDto, locale: Locale): string | null {
  if (profile.source !== "factory" || profile.speaker_type === null) {
    return null;
  }
  return translateSpeakerType(locale, profile.speaker_type);
}

/** A factory preset's name in `locale`, built from its car model and
 * speaker type. The function never translates a custom (user-created)
 * profile's name: it is the name the user typed. */
export function localizedProfileName(profile: ProfileDto, locale: Locale): string {
  if (profile.source !== "factory" || profile.car_model === null || profile.speaker_type === null) {
    return profile.name;
  }
  const model = translateModelName(locale, profile.car_model);
  const speakerType = translateSpeakerType(locale, profile.speaker_type);
  return `${model} — ${speakerType}`;
}
