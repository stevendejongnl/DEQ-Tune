import { describe, expect, it } from "vitest";
import {
  applyDisplay,
  FOLLOW_THE_DEVICE,
  readDisplayChoices,
  resolveDisplay,
  saveDisplayChoices,
  type DisplayEnvironment,
} from "./display-mode.ts";
import { createFakeLocaleStorage } from "../i18n/testing/fake-locale-storage.ts";

function environment(matching: string[] = [], fontSizePx = 16): DisplayEnvironment {
  return {
    matches: (query) => matching.includes(query),
    defaultFontSizePx: () => fontSizePx,
  };
}

describe("resolveDisplay", () => {
  it("stays dark, normal and plain with no signal from the device", () => {
    expect(resolveDisplay(FOLLOW_THE_DEVICE, environment())).toEqual({
      scheme: "dark",
      contrast: "normal",
      text: "normal",
      reading: "normal",
    });
  });

  it("follows a device that asks for light, more contrast and large text", () => {
    const device = environment(["(prefers-color-scheme: light)", "(prefers-contrast: more)"], 20);

    expect(resolveDisplay(FOLLOW_THE_DEVICE, device)).toEqual({
      scheme: "light",
      contrast: "more",
      text: "large",
      reading: "normal",
    });
  });

  it("treats forced colors as a request for more contrast", () => {
    expect(resolveDisplay(FOLLOW_THE_DEVICE, environment(["(forced-colors: active)"])).contrast).toBe("more");
  });

  it("lets a fixed choice win over the device", () => {
    const device = environment(["(prefers-color-scheme: light)"], 24);

    expect(resolveDisplay({ scheme: "dark", contrast: "more", text: "normal", reading: "easy" }, device)).toEqual({
      scheme: "dark",
      contrast: "more",
      text: "normal",
      reading: "easy",
    });
  });
});

describe("the stored choices", () => {
  it("follow the device when nothing is stored", () => {
    expect(readDisplayChoices(createFakeLocaleStorage({}))).toEqual(FOLLOW_THE_DEVICE);
  });

  it("come back as they were saved", () => {
    const storage = createFakeLocaleStorage({});
    saveDisplayChoices(storage, { scheme: "light", contrast: "device", text: "large", reading: "easy" });

    expect(readDisplayChoices(storage)).toEqual({ scheme: "light", contrast: "device", text: "large", reading: "easy" });
  });

  it("follow the device for a value they do not know", () => {
    const storage = createFakeLocaleStorage({});
    storage.setItem("deq-tune.display", '{"scheme":"sepia","text":3}');

    expect(readDisplayChoices(storage)).toEqual(FOLLOW_THE_DEVICE);
  });

  it("survive a broken stored value", () => {
    const storage = createFakeLocaleStorage({});
    storage.setItem("deq-tune.display", "{not json");

    expect(readDisplayChoices(storage)).toEqual(FOLLOW_THE_DEVICE);
  });
});

describe("applyDisplay", () => {
  it("writes one data attribute per axis", () => {
    const root = document.createElement("html");

    applyDisplay({ scheme: "light", contrast: "more", text: "large", reading: "easy" }, root);

    expect(root.dataset).toMatchObject({ scheme: "light", contrast: "more", text: "large", reading: "easy" });
  });
});
