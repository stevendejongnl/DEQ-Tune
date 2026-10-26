import { describe, expect, it } from "vitest";
import "./display-settings.ts";
import type { DisplaySettings } from "./display-settings.ts";
import { DisplayController } from "../display/display-controller.ts";
import { createFakeLocaleStorage } from "../i18n/testing/fake-locale-storage.ts";

function controller(): { controller: DisplayController; root: HTMLElement } {
  const root = document.createElement("html");
  const device = { matches: () => false, defaultFontSizePx: () => 16 };
  const instance = new DisplayController(createFakeLocaleStorage({}), device, root, () => {});
  instance.start();
  return { controller: instance, root };
}

async function mount(displayController: DisplayController): Promise<DisplaySettings> {
  const element = document.createElement("display-settings") as DisplaySettings;
  element.controller = displayController;
  document.body.append(element);
  await element.updateComplete;
  return element;
}

describe("display-settings", () => {
  it("offers four choices, three of them following the device", async () => {
    const { controller: displayController } = controller();
    const element = await mount(displayController);

    const selects = [...element.shadowRoot!.querySelectorAll("select")];
    expect(selects.map((select) => select.name)).toEqual(["scheme", "contrast", "text", "reading"]);
    expect(selects.slice(0, 3).map((select) => select.value)).toEqual(["device", "device", "device"]);
    expect(selects[3].value).toBe("normal");
  });

  it("applies a choice at once", async () => {
    const { controller: displayController, root } = controller();
    const element = await mount(displayController);

    element.choose("reading", "easy");
    element.choose("scheme", "light");
    await element.updateComplete;

    expect(root.dataset.reading).toBe("easy");
    expect(root.dataset.scheme).toBe("light");
    expect(element.shadowRoot!.querySelector<HTMLSelectElement>('select[name="scheme"]')!.value).toBe("light");
  });
});
