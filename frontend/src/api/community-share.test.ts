import { describe, expect, it } from "vitest";
import type { LibraryExportDto } from "../dto/profile.dto.ts";
import { blankTuningData } from "../dto/blank-tuning.ts";
import {
  buildShareEntry,
  COMMUNITY_REPOSITORY_URL,
  MAXIMUM_PREFILLED_URL_LENGTH,
  newFileUrl,
  ShareError,
  slug,
} from "./community-share.ts";

function library(): LibraryExportDto {
  return {
    format: "deq-tune-library",
    version: 1,
    profiles: [
      {
        name: "My CX-5",
        brand_name: "Mazda",
        car_model: "cx_5_2019",
        speaker_type: "bose",
        supported_processors: [],
        favorite: true,
        data: blankTuningData(),
      },
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

const DETAILS = { author: "someone", description: "Softer highs at night." };

describe("slug", () => {
  it("follows the library's own rule", () => {
    expect(slug("Night drive")).toBe("night-drive");
    expect(slug("  CX-5 (2019)! ")).toBe("cx-5-2019");
  });
});

describe("buildShareEntry", () => {
  it("writes an EQ the way tools/add_entry.py does", () => {
    const entry = buildShareEntry(library(), { kind: "equalizer", name: "Night drive" }, DETAILS);

    expect(entry.path).toBe("equalizers/night-drive.json");
    expect(JSON.parse(entry.content)).toEqual({
      author: "someone",
      description: "Softer highs at night.",
      equalizer: { name: "Night drive", gains: [1, 0, -1] },
    });
    expect(entry.content.endsWith("}\n")).toBe(true);
    expect(entry.content).toContain('\n  "author"');
  });

  it("files a profile under its brand and car model, without its star", () => {
    const entry = buildShareEntry(library(), { kind: "profile", name: "My CX-5" }, DETAILS);

    expect(entry.path).toBe("profiles/mazda/cx-5-2019/my-cx-5.json");
    const profile = JSON.parse(entry.content).profile;
    expect(profile.favorite).toBeUndefined();
    expect(profile.speaker_type).toBe("bose");
  });

  it("takes a missing brand and model from the details", () => {
    const entry = buildShareEntry(library(), { kind: "profile", name: "Dusty" }, {
      ...DETAILS,
      brand: "Dacia",
      model: "Duster 2021",
    });

    expect(entry.path).toBe("profiles/dacia/duster-2021/dusty.json");
    expect(JSON.parse(entry.content).profile.brand_name).toBe("Dacia");
  });

  it("refuses a profile with no brand or model", () => {
    expect(() => buildShareEntry(library(), { kind: "profile", name: "Dusty" }, DETAILS)).toThrow(ShareError);
  });

  it("refuses an entry with no author or description", () => {
    const choice = { kind: "equalizer", name: "Night drive" } as const;
    expect(() => buildShareEntry(library(), choice, { author: " ", description: "x" })).toThrow(ShareError);
    expect(() => buildShareEntry(library(), choice, { author: "x", description: "" })).toThrow(ShareError);
  });
});

describe("newFileUrl", () => {
  it("fills a small entry into GitHub's new-file page", () => {
    const { url, prefilled } = newFileUrl({ path: "equalizers/a.json", content: '{"a": 1}\n' });

    expect(prefilled).toBe(true);
    expect(url.startsWith(`${COMMUNITY_REPOSITORY_URL}/new/main?filename=equalizers%2Fa.json&value=`)).toBe(true);
    expect(decodeURIComponent(new URL(url).searchParams.get("value")!)).toBe('{"a": 1}\n');
  });

  it("leaves a big entry out of the URL", () => {
    const { url, prefilled } = newFileUrl({ path: "profiles/a/b/c.json", content: "x".repeat(MAXIMUM_PREFILLED_URL_LENGTH) });

    expect(prefilled).toBe(false);
    expect(url).not.toContain("value=");
  });
});
