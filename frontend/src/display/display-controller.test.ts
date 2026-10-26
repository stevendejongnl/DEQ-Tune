import { describe, expect, it } from "vitest";
import { DisplayController } from "./display-controller.ts";
import type { DisplayEnvironment } from "./display-mode.ts";
import { createFakeLocaleStorage } from "../i18n/testing/fake-locale-storage.ts";

class FakeDevice implements DisplayEnvironment {
  matching = new Set<string>();
  onChange: (() => void) | null = null;

  matches(query: string): boolean {
    return this.matching.has(query);
  }

  defaultFontSizePx(): number {
    return 16;
  }
}

function setUp(stored: Record<string, string> = {}) {
  const device = new FakeDevice();
  const storage = createFakeLocaleStorage(stored);
  const root = document.createElement("html");
  const controller = new DisplayController(storage, device, root, (_queries, onChange) => {
    device.onChange = onChange;
  });
  return { device, storage, root, controller };
}

describe("DisplayController", () => {
  it("starts dark with no signal and no choice", () => {
    const { root, controller } = setUp();

    controller.start();

    expect(root.dataset.scheme).toBe("dark");
    expect(root.dataset.reading).toBe("normal");
  });

  it("follows the device when it switches to light", () => {
    const { device, root, controller } = setUp();
    controller.start();

    device.matching.add("(prefers-color-scheme: light)");
    device.onChange!();

    expect(root.dataset.scheme).toBe("light");
  });

  it("keeps a fixed choice when the device switches", () => {
    const { device, root, controller } = setUp();
    controller.start();
    controller.choose({ scheme: "dark" });

    device.matching.add("(prefers-color-scheme: light)");
    device.onChange!();

    expect(root.dataset.scheme).toBe("dark");
  });

  it("stores a choice for the next visit", () => {
    const { storage, controller } = setUp();

    controller.choose({ reading: "easy" });

    const next = new DisplayController(storage, new FakeDevice(), document.createElement("html"), () => {});
    expect(next.choices.reading).toBe("easy");
  });
});
