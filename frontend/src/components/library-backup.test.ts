import { afterEach, describe, expect, it } from "vitest";
import { ApiError } from "../api/client.ts";
import type { LibraryExportDto } from "../dto/profile.dto.ts";
import { sampleTuningData } from "../dto/testing/sample-profile.ts";
import "./library-backup.ts";
import { libraryFileName, type LibraryBackup } from "./library-backup.ts";
import { FakeLibraryApi } from "./testing/fake-library-api.ts";

function libraryWith(profileNames: string[], equalizerNames: string[] = []): LibraryExportDto {
  return {
    format: "deq-tune-library",
    version: 1,
    profiles: profileNames.map((name) => ({
      name,
      brand_name: null,
      car_model: null,
      speaker_type: null,
      supported_processors: [],
      favorite: false,
      data: sampleTuningData(),
    })),
    equalizers: equalizerNames.map((name) => ({ name, favorite: false, gains: new Array(13).fill(0) })),
    starred_factory_profiles: [],
    starred_factory_equalizers: [],
  };
}

const savedFiles: { fileName: string; text: string }[] = [];

async function mount(api: FakeLibraryApi, saveAnswer = true): Promise<LibraryBackup> {
  const element = document.createElement("library-backup") as LibraryBackup;
  element.api = api;
  element.saveFile = async (fileName, text) => {
    savedFiles.push({ fileName, text });
    return saveAnswer;
  };
  element.now = () => new Date("2026-10-23T21:00:00Z");
  document.body.append(element);
  await element.updateComplete;
  return element;
}

function message(element: LibraryBackup): string {
  return element.shadowRoot!.querySelector(".message")?.textContent ?? "";
}

afterEach(() => {
  document.body.replaceChildren();
  savedFiles.length = 0;
});

describe("library-backup", () => {
  it("saves the library as a dated JSON file", async () => {
    const element = await mount(new FakeLibraryApi(libraryWith(["Dusty"], ["Night drive"])));

    element.shadowRoot!.querySelector<HTMLButtonElement>(".export")!.click();
    await new Promise((resolve) => setTimeout(resolve));
    await element.updateComplete;

    expect(savedFiles.map((file) => file.fileName)).toEqual(["deq-tune-library-2026-10-23.json"]);
    expect(JSON.parse(savedFiles[0].text).profiles[0].name).toBe("Dusty");
    expect(message(element)).toBe("Saved 1 profiles and 1 EQs.");
  });

  it("says so when the person cancels the save", async () => {
    const element = await mount(new FakeLibraryApi(libraryWith(["Dusty"])), false);

    element.shadowRoot!.querySelector<HTMLButtonElement>(".export")!.click();
    await new Promise((resolve) => setTimeout(resolve));
    await element.updateComplete;

    expect(message(element)).toBe("Not saved.");
  });

  it("adds a file's library and tells app-root to read its lists again", async () => {
    const api = new FakeLibraryApi(libraryWith(["Dusty"]));
    const element = await mount(api);
    let imported = 0;
    element.addEventListener("library-imported", () => (imported += 1));

    await element.importText(JSON.stringify(libraryWith(["Dusty", "Mazda tweak"], ["Night drive"])));
    await element.updateComplete;

    expect(api.library.profiles.map((profile) => profile.name)).toEqual(["Dusty", "Mazda tweak"]);
    expect(message(element)).toBe("Added 1 profiles and 1 EQs. 1 were there already.");
    expect(imported).toBe(1);
  });

  it("fires nothing when the file added nothing", async () => {
    const element = await mount(new FakeLibraryApi(libraryWith(["Dusty"])));
    let imported = 0;
    element.addEventListener("library-imported", () => (imported += 1));

    await element.importText(JSON.stringify(libraryWith(["Dusty"])));

    expect(imported).toBe(0);
  });

  it.each([
    ["text that is not JSON", "not json {"],
    ["JSON of another kind", JSON.stringify({ format: "something-else", version: 1 })],
  ])("says so for %s", async (_label, text) => {
    const element = await mount(new FakeLibraryApi(libraryWith([])));

    await element.importText(text);
    await element.updateComplete;

    expect(message(element)).toContain("not a DEQ Tune library");
  });

  it("says that the Pi did not answer when it is out of reach", async () => {
    const api = new FakeLibraryApi(libraryWith([]));
    api.failWith = new ApiError(503, "unreachable");
    const element = await mount(api);

    await element.importText(JSON.stringify(libraryWith(["Dusty"])));
    await element.updateComplete;

    expect(message(element)).toBe("The Pi did not answer. Try again.");
  });

  it("names the file after the day", () => {
    expect(libraryFileName(new Date("2026-01-02T03:04:05Z"))).toBe("deq-tune-library-2026-01-02.json");
  });
});
