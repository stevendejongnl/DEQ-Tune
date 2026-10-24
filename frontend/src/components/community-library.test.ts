import { afterEach, describe, expect, it } from "vitest";
import { ApiError } from "../api/client.ts";
import type { CommunityEntry } from "../api/community-library.ts";
import type { LibraryExportDto } from "../dto/profile.dto.ts";
import { sampleTuningData } from "../dto/testing/sample-profile.ts";
import "./community-library.ts";
import { curvePoints, type CommunityLibrary } from "./community-library.ts";
import { FakeCommunityLibrary } from "./testing/fake-community-library.ts";
import { FakeLibraryApi } from "./testing/fake-library-api.ts";

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

function emptyLibrary(): LibraryExportDto {
  return {
    format: "deq-tune-library",
    version: 1,
    profiles: [],
    equalizers: [],
    starred_factory_profiles: [],
    starred_factory_equalizers: [],
  };
}

async function settle(element: CommunityLibrary): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve));
  await element.updateComplete;
}

async function mount(community: FakeCommunityLibrary, api = new FakeLibraryApi(emptyLibrary())): Promise<CommunityLibrary> {
  const element = document.createElement("community-library") as CommunityLibrary;
  element.api = api;
  element.community = community;
  document.body.append(element);
  await settle(element);
  return element;
}

function shownIds(element: CommunityLibrary): string[] {
  return [...element.shadowRoot!.querySelectorAll<HTMLElement>(".entry")].map((entry) => entry.dataset.id ?? "");
}

function entryElement(element: CommunityLibrary, id: string): HTMLElement {
  return element.shadowRoot!.querySelector<HTMLElement>(`.entry[data-id="${id}"]`)!;
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("community-library", () => {
  it("lists every entry, with a curve for an EQ and a warning for a profile", async () => {
    const element = await mount(new FakeCommunityLibrary([nightDrive, daily]));

    expect(shownIds(element)).toEqual([nightDrive.id, daily.id]);
    expect(entryElement(element, nightDrive.id).querySelector(".curve")).not.toBeNull();
    expect(entryElement(element, nightDrive.id).querySelector(".warning")).toBeNull();
    expect(entryElement(element, daily.id).querySelector(".car")!.textContent).toBe("Mazda CX-5");
    expect(entryElement(element, daily.id).querySelector(".warning")).not.toBeNull();
  });

  it("filters by kind and by search", async () => {
    const element = await mount(new FakeCommunityLibrary([nightDrive, daily]));
    const kindButtons = element.shadowRoot!.querySelectorAll<HTMLButtonElement>(".kinds button");

    kindButtons[2].click();
    await element.updateComplete;
    expect(shownIds(element)).toEqual([daily.id]);

    kindButtons[0].click();
    const search = element.shadowRoot!.querySelector<HTMLInputElement>(".search")!;
    search.value = "motorway";
    search.dispatchEvent(new Event("input"));
    await element.updateComplete;
    expect(shownIds(element)).toEqual([nightDrive.id]);
  });

  it("adds an entry to the library and tells app-root", async () => {
    const api = new FakeLibraryApi(emptyLibrary());
    const element = await mount(new FakeCommunityLibrary([nightDrive]), api);
    let imported = 0;
    element.addEventListener("library-imported", () => (imported += 1));

    entryElement(element, nightDrive.id).querySelector<HTMLButtonElement>(".add")!.click();
    await settle(element);

    expect(api.library.equalizers.map((equalizer) => equalizer.name)).toEqual(["Night drive"]);
    expect(imported).toBe(1);
    expect(entryElement(element, nightDrive.id).querySelector(".message")!.textContent).toBe("Added.");
    expect(entryElement(element, nightDrive.id).querySelector<HTMLButtonElement>(".add")!.disabled).toBe(true);
  });

  it("says so when the library holds the entry already", async () => {
    const library = emptyLibrary();
    library.equalizers = [{ name: "Night drive", favorite: false, gains: new Array(13).fill(1) }];
    const element = await mount(new FakeCommunityLibrary([nightDrive]), new FakeLibraryApi(library));

    entryElement(element, nightDrive.id).querySelector<HTMLButtonElement>(".add")!.click();
    await settle(element);

    expect(entryElement(element, nightDrive.id).querySelector(".message")!.textContent).toBe("In your library already.");
  });

  it("says so when the Pi does not answer", async () => {
    const api = new FakeLibraryApi(emptyLibrary());
    api.failWith = new ApiError(503, "down");
    const element = await mount(new FakeCommunityLibrary([nightDrive]), api);

    entryElement(element, nightDrive.id).querySelector<HTMLButtonElement>(".add")!.click();
    await settle(element);

    expect(entryElement(element, nightDrive.id).querySelector(".message")!.textContent).toBe(
      "The Pi did not answer. Try again.",
    );
  });

  it("offers a retry when the library does not load", async () => {
    const community = new FakeCommunityLibrary([nightDrive]);
    community.failing = true;
    const element = await mount(community);

    expect(element.shadowRoot!.querySelector(".empty")!.textContent).toContain("needs internet");

    community.failing = false;
    element.shadowRoot!.querySelector<HTMLButtonElement>(".retry")!.click();
    await settle(element);
    expect(shownIds(element)).toEqual([nightDrive.id]);
    expect(community.reads).toBe(2);
  });

  it("says so when the library has no entries", async () => {
    const element = await mount(new FakeCommunityLibrary([]));

    expect(element.shadowRoot!.querySelector(".empty")!.textContent).toBe("No entries here yet.");
  });
});

describe("curvePoints", () => {
  it("puts 0 dB in the middle and +12 dB near the top", () => {
    expect(curvePoints([0, 12, -12])).toBe("0.0,16.0 60.0,2.0 120.0,30.0");
  });
});
