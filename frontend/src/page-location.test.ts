import { describe, expect, it } from "vitest";
import { pageLocationHash, parsePageLocation } from "./page-location.ts";

describe("pageLocationHash", () => {
  it("names the page, the phone tab and the settings section", () => {
    expect(pageLocationHash({ page: "settings", phoneTab: "eq", settingsSection: "phone" })).toBe(
      "#page=settings&tab=eq&section=phone",
    );
  });
});

describe("pageLocationHash with a chosen language", () => {
  it("adds the language", () => {
    expect(pageLocationHash({ page: "sound", phoneTab: "audio", settingsSection: "language", locale: "nl" })).toBe(
      "#page=sound&tab=audio&section=language&lang=nl",
    );
  });
});

describe("parsePageLocation", () => {
  it("reads back what pageLocationHash wrote", () => {
    const location = { page: "car", phoneTab: "car", settingsSection: "wifi", locale: "de" } as const;
    expect(parsePageLocation(pageLocationHash(location))).toEqual(location);
  });

  it("keeps only the known values", () => {
    expect(parsePageLocation("#page=nowhere&tab=eq&section=secret&lang=xx")).toEqual({ phoneTab: "eq" });
  });

  it("gives nothing for an empty hash", () => {
    expect(parsePageLocation("")).toEqual({});
  });
});
