import type { LibraryEqualizerDto, LibraryExportDto, LibraryProfileDto } from "../dto/profile.dto.ts";

/** The repository that holds the community library. */
export const COMMUNITY_REPOSITORY_URL = "https://github.com/stevendejongnl/deq-tune-library";

/** GitHub fills a new file from the URL. A longer URL than this risks a
 * refused request, so a bigger entry goes through the clipboard instead. */
export const MAXIMUM_PREFILLED_URL_LENGTH = 8000;

/** What a person shares: one of their own EQs or car profiles, by name. */
export type ShareChoice = { kind: "equalizer"; name: string } | { kind: "profile"; name: string };

export interface ShareDetails {
  author: string;
  description: string;
  /** For a profile with no brand in the backup. */
  brand?: string;
  /** For a profile with no car model in the backup. */
  model?: string;
}

/** One entry file, at its place in the library repository. */
export interface ShareEntry {
  path: string;
  content: string;
}

export class ShareError extends Error {}

/** The library's file and directory names: lower case, words joined by `-`.
 * The same rule as `slug` in the repository's `tools/library.py`. */
export function slug(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * Builds the entry file for one item of a backup, the way the repository's
 * `tools/add_entry.py` does: the same place, the same keys and the same
 * two-space indent.
 */
export function buildShareEntry(
  library: LibraryExportDto,
  choice: ShareChoice,
  details: ShareDetails,
): ShareEntry {
  const author = details.author.trim();
  const description = details.description.trim();
  if (author === "" || description === "") {
    throw new ShareError("an entry needs an author and a description");
  }
  if (choice.kind === "equalizer") {
    const equalizer = findItem(library.equalizers, choice.name);
    return entryFile(`equalizers/${slug(equalizer.name)}.json`, {
      author,
      description,
      equalizer: { name: equalizer.name, gains: equalizer.gains },
    });
  }
  const profile = findItem(library.profiles, choice.name);
  const brand = profile.brand_name ?? emptyAsNull(details.brand);
  const model = profile.car_model ?? emptyAsNull(details.model);
  if (brand === null || model === null) {
    throw new ShareError("a car profile needs a brand and a car model");
  }
  // The library leaves out the star: a person adds an entry without one.
  const shared: Partial<LibraryProfileDto> = { ...profile, brand_name: brand, car_model: model };
  delete shared.favorite;
  return entryFile(`profiles/${slug(brand)}/${slug(model)}/${slug(profile.name)}.json`, {
    author,
    description,
    profile: shared,
  });
}

/** GitHub's page for a new file in the library, with the file filled in when
 * the URL stays short enough. GitHub offers a fork to a person who cannot
 * write to the repository. */
export function newFileUrl(entry: ShareEntry): { url: string; prefilled: boolean } {
  const base = `${COMMUNITY_REPOSITORY_URL}/new/main?filename=${encodeURIComponent(entry.path)}`;
  const prefilled = `${base}&value=${encodeURIComponent(entry.content)}`;
  if (prefilled.length <= MAXIMUM_PREFILLED_URL_LENGTH) {
    return { url: prefilled, prefilled: true };
  }
  return { url: base, prefilled: false };
}

function findItem<Item extends LibraryEqualizerDto | LibraryProfileDto>(items: Item[], name: string): Item {
  const item = items.find((candidate) => candidate.name === name);
  if (item === undefined) {
    throw new ShareError(`no item named ${name}`);
  }
  return item;
}

function emptyAsNull(text: string | undefined): string | null {
  const trimmed = text?.trim() ?? "";
  return trimmed === "" ? null : trimmed;
}

function entryFile(path: string, entry: object): ShareEntry {
  return { path, content: `${JSON.stringify(entry, null, 2)}\n` };
}
