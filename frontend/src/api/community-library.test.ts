import { describe, expect, it } from "vitest";
import { sampleTuningData } from "../dto/testing/sample-profile.ts";
import {
  COMMUNITY_LIBRARY_URL,
  CommunityLibraryClient,
  CommunityLibraryError,
  entryCar,
  entryMatches,
  libraryWithEntry,
  type CommunityEntry,
} from "./community-library.ts";
import { createFakeFetch, jsonResponse } from "./testing/fake-fetch.ts";

const nightDrive: CommunityEntry = {
  id: "equalizers/night-drive",
  kind: "equalizer",
  author: "someone",
  description: "Calm highs for the motorway.",
  equalizer: { name: "Night drive", gains: new Array(13).fill(1) },
};

const daily: CommunityEntry = {
  id: "profiles/mazda/cx-5/daily",
  kind: "profile",
  author: "another",
  description: "Bose system.",
  profile: {
    name: "Daily",
    brand_name: "Mazda",
    car_model: "CX-5",
    speaker_type: null,
    supported_processors: [],
    data: sampleTuningData(),
  },
};

describe("CommunityLibraryClient", () => {
  it("reads the published index", async () => {
    const index = { format: "deq-tune-community", version: 1, entries: [nightDrive, daily] };
    const fake = createFakeFetch(() => jsonResponse(index));

    const read = await new CommunityLibraryClient(fake.fetch).readIndex();

    expect(read.entries.map((entry) => entry.id)).toEqual([nightDrive.id, daily.id]);
    expect(fake.calls[0].url).toBe(COMMUNITY_LIBRARY_URL);
  });

  it("refuses an index of a newer version", async () => {
    const fake = createFakeFetch(() => jsonResponse({ format: "deq-tune-community", version: 2, entries: [] }));

    await expect(new CommunityLibraryClient(fake.fetch).readIndex()).rejects.toThrow();
  });

  it("fails on an answer that is not OK", async () => {
    const fake = createFakeFetch(() => jsonResponse({}, 404));

    await expect(new CommunityLibraryClient(fake.fetch).readIndex()).rejects.toBeInstanceOf(CommunityLibraryError);
  });
});

describe("libraryWithEntry", () => {
  it("makes a library file with the one EQ, without a star", () => {
    const library = libraryWithEntry(nightDrive);

    expect(library.format).toBe("deq-tune-library");
    expect(library.profiles).toEqual([]);
    expect(library.equalizers).toEqual([{ name: "Night drive", gains: new Array(13).fill(1), favorite: false }]);
  });

  it("makes a library file with the one profile", () => {
    const library = libraryWithEntry(daily);

    expect(library.equalizers).toEqual([]);
    expect(library.profiles.map((profile) => [profile.name, profile.favorite])).toEqual([["Daily", false]]);
  });
});

describe("entryMatches", () => {
  it("finds an entry by its car, ignoring case", () => {
    expect(entryMatches(daily, "cx-5")).toBe(true);
    expect(entryMatches(nightDrive, "cx-5")).toBe(false);
  });

  it("matches every entry for an empty search", () => {
    expect(entryMatches(nightDrive, "  ")).toBe(true);
  });
});

describe("entryCar", () => {
  it("names a profile's car and gives an EQ none", () => {
    expect(entryCar(daily)).toBe("Mazda CX-5");
    expect(entryCar(nightDrive)).toBe("");
  });
});
