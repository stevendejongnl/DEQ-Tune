import { describe, expect, it } from "vitest";
import "./community-share-form.ts";
import type { CommunityShareForm } from "./community-share-form.ts";
import { blankTuningData } from "../dto/blank-tuning.ts";
import type { LibraryExportDto } from "../dto/profile.dto.ts";
import { FakeLibraryApi } from "./testing/fake-library-api.ts";

function library(): LibraryExportDto {
  return {
    format: "deq-tune-library",
    version: 1,
    profiles: [
      {
        name: "Dusty",
        brand_name: null,
        car_model: null,
        speaker_type: null,
        supported_processors: [],
        favorite: false,
        data: blankTuningData(),
      },
    ],
    equalizers: [{ name: "Night drive", favorite: true, gains: [1, 0, -1] }],
    starred_factory_profiles: [],
    starred_factory_equalizers: [],
  };
}

async function mountOpen(api: FakeLibraryApi, copied: string[] = []): Promise<CommunityShareForm> {
  const element = document.createElement("community-share-form") as CommunityShareForm;
  element.api = api;
  element.copyText = async (text) => {
    copied.push(text);
  };
  document.body.append(element);
  await element.updateComplete;
  await element.open();
  await element.updateComplete;
  return element;
}

function shadow(element: CommunityShareForm): ShadowRoot {
  return element.shadowRoot!;
}

describe("community-share-form", () => {
  it("starts as one button", async () => {
    const element = document.createElement("community-share-form") as CommunityShareForm;
    document.body.append(element);
    await element.updateComplete;

    expect(shadow(element).querySelector("button.open")!.textContent).toContain("Share your own");
    expect(shadow(element).querySelector("form")).toBeNull();
  });

  it("lists the person's own EQs and profiles", async () => {
    const element = await mountOpen(new FakeLibraryApi(library()));

    const labels = [...shadow(element).querySelectorAll("optgroup")].map((group) => group.label);
    expect(labels).toEqual(["Your EQs", "Your car profiles"]);
    expect(shadow(element).querySelector("option")!.textContent).toBe("Night drive");
  });

  it("links to GitHub's new-file page with the EQ filled in", async () => {
    const element = await mountOpen(new FakeLibraryApi(library()));
    element.setDetails({ author: "someone", description: "Softer highs at night." });

    element.make();
    await element.updateComplete;

    const link = shadow(element).querySelector<HTMLAnchorElement>("a.github")!;
    const url = new URL(link.href);
    expect(url.pathname).toBe("/stevendejongnl/deq-tune-library/new/main");
    expect(url.searchParams.get("filename")).toBe("equalizers/night-drive.json");
    expect(JSON.parse(url.searchParams.get("value")!).equalizer.name).toBe("Night drive");
    expect(link.target).toBe("_blank");
  });

  it("asks for a brand and model when the profile has none", async () => {
    const element = await mountOpen(new FakeLibraryApi(library()));
    element.pick("profile:Dusty");
    await element.updateComplete;

    expect(shadow(element).querySelector('input[name="brand"]')).not.toBeNull();
    expect(shadow(element).querySelector('input[name="model"]')).not.toBeNull();

    element.setDetails({ author: "someone", description: "Duster 2021." });
    element.make();
    await element.updateComplete;
    expect(shadow(element).querySelector(".message")!.textContent).toContain("brand and model");
  });

  it("offers a long entry to copy, and opens the page without it", async () => {
    const big = library();
    big.equalizers[0].gains = Array.from({ length: 2000 }, () => 0.5);
    const copied: string[] = [];
    const element = await mountOpen(new FakeLibraryApi(big), copied);
    element.setDetails({ author: "someone", description: "A long one." });

    element.make();
    await element.updateComplete;
    shadow(element).querySelector<HTMLButtonElement>("button.copy")!.click();
    await new Promise((resolve) => setTimeout(resolve));
    await element.updateComplete;

    expect(new URL(shadow(element).querySelector<HTMLAnchorElement>("a.github")!.href).searchParams.has("value")).toBe(false);
    expect(copied).toHaveLength(1);
    expect(JSON.parse(copied[0]).author).toBe("someone");
    expect(shadow(element).querySelector("button.copy")!.textContent).toContain("Copied");
  });

  it("says so when the Pi does not hand over the library", async () => {
    const api = new FakeLibraryApi(library());
    api.failWith = new Error("offline");

    const element = await mountOpen(api);

    expect(shadow(element).querySelector(".message")!.textContent).toContain("could not read your library");
  });
});
