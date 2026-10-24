import typia from "typia";
import type { LibraryEqualizerDto, LibraryExportDto, LibraryProfileDto } from "../dto/profile.dto.ts";
import type { FetchLike } from "./client.ts";

/** The index that the deq-tune-library repository publishes on GitHub Pages.
 * Its `tools/build_index.py` writes this shape. */
export const COMMUNITY_LIBRARY_URL = "https://stevendejongnl.github.io/deq-tune-library/index.json";

/** Where a person reads how to add an entry of their own. */
export const COMMUNITY_CONTRIBUTING_URL = "https://github.com/stevendejongnl/deq-tune-library/blob/main/CONTRIBUTING.md";

interface CommunityEntryBase {
  /** The entry's path in the repository, without `.json`. */
  id: string;
  author: string;
  description: string;
}

/** The index drops `favorite`: the app adds an entry without a star. */
export interface CommunityEqualizerEntry extends CommunityEntryBase {
  kind: "equalizer";
  equalizer: Omit<LibraryEqualizerDto, "favorite">;
}

export interface CommunityProfileEntry extends CommunityEntryBase {
  kind: "profile";
  profile: Omit<LibraryProfileDto, "favorite">;
}

export type CommunityEntry = CommunityEqualizerEntry | CommunityProfileEntry;

export interface CommunityIndex {
  format: "deq-tune-community";
  /** A newer index fails the check, so an old app does not misread it. */
  version: 1;
  entries: CommunityEntry[];
}

export interface CommunityLibraryApi {
  readIndex(): Promise<CommunityIndex>;
}

export class CommunityLibraryError extends Error {}

/**
 * Reads the community library's index from the internet.
 *
 * The browser reads it, not the Pi: the phone or the computer has internet,
 * and the Pi in the car often does not. Call `readIndex()`. It depends on a
 * fetch function, which a test replaces.
 */
export class CommunityLibraryClient implements CommunityLibraryApi {
  private readonly fetchFunction: FetchLike;
  private readonly url: string;

  constructor(fetchFunction: FetchLike = (url, init) => fetch(url, init), url: string = COMMUNITY_LIBRARY_URL) {
    this.fetchFunction = fetchFunction;
    this.url = url;
  }

  async readIndex(): Promise<CommunityIndex> {
    const response = await this.fetchFunction(this.url, { cache: "no-cache" });
    if (!response.ok) {
      throw new CommunityLibraryError(`${this.url} answered ${response.status}`);
    }
    return typia.assert<CommunityIndex>(await response.json());
  }
}

/** A library file with one entry, for the backend's import. */
export function libraryWithEntry(entry: CommunityEntry): LibraryExportDto {
  return {
    format: "deq-tune-library",
    version: 1,
    profiles: entry.kind === "profile" ? [{ ...entry.profile, favorite: false }] : [],
    equalizers: entry.kind === "equalizer" ? [{ ...entry.equalizer, favorite: false }] : [],
    starred_factory_profiles: [],
    starred_factory_equalizers: [],
  };
}

export function entryName(entry: CommunityEntry): string {
  return entry.kind === "equalizer" ? entry.equalizer.name : entry.profile.name;
}

/** The car of a profile, as "Mazda CX-5". An EQ has none. */
export function entryCar(entry: CommunityEntry): string {
  if (entry.kind === "equalizer") {
    return "";
  }
  return [entry.profile.brand_name, entry.profile.car_model].filter((part) => part !== null).join(" ");
}

/** True when the entry's name, car, author or description holds `search`. */
export function entryMatches(entry: CommunityEntry, search: string): boolean {
  const wanted = search.trim().toLowerCase();
  if (wanted === "") {
    return true;
  }
  return [entryName(entry), entryCar(entry), entry.author, entry.description].some((text) =>
    text.toLowerCase().includes(wanted),
  );
}
