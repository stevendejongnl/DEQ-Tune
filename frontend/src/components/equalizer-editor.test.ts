import { describe, expect, it } from "vitest";
import "./equalizer-editor.ts";
import type { EqualizerEditor } from "./equalizer-editor.ts";
import type { EqualizerDto } from "../dto/profile.dto.ts";

const MINE: EqualizerDto = {
  id: 7,
  name: "Mine",
  source: "custom",
  favorite: false,
  gains: new Array(13).fill(0),
};
const SUPER_BASS: EqualizerDto = {
  id: 2,
  name: "Super Bass",
  source: "factory",
  favorite: true,
  gains: [8, 8, 6, 6, 2, 0, 0, 0, 0, 2, 2, 4, 2],
};

async function mount(equalizer: EqualizerDto | null): Promise<EqualizerEditor> {
  const element = document.createElement("equalizer-editor") as EqualizerEditor;
  element.equalizer = equalizer;
  document.body.append(element);
  await element.updateComplete;
  return element;
}

function collect<T>(element: EqualizerEditor, type: string): T[] {
  const details: T[] = [];
  element.addEventListener(type, (rawEvent) => details.push((rawEvent as CustomEvent<T>).detail));
  return details;
}

function chart(element: EqualizerEditor) {
  return element.shadowRoot!.querySelector("eq-editor")!;
}

describe("equalizer-editor", () => {
  it("draws the EQ that plays, titled with its name, with no factory curve behind it", async () => {
    const element = await mount(SUPER_BASS);

    expect(chart(element).gains).toEqual(SUPER_BASS.gains);
    expect(chart(element).factoryGains).toEqual([]);
    expect(chart(element).heading).toBe("Super Bass");
  });

  it("draws a flat curve for No EQ", async () => {
    const element = await mount(null);

    expect(chart(element).gains).toEqual(new Array(13).fill(0));
    expect(chart(element).heading).toBe("No EQ");
  });

  it("turns a band change into the whole new curve", async () => {
    const element = await mount(SUPER_BASS);
    const changes = collect<{ gains: number[] }>(element, "equalizer-gains");

    chart(element).dispatchEvent(new CustomEvent("gain-change", { detail: { band: 2, value: 1 } }));

    expect(changes).toEqual([{ gains: [8, 8, 1, 6, 2, 0, 0, 0, 0, 2, 2, 4, 2] }]);
  });

  it("says that a drag of a factory EQ makes a copy, and offers no name or delete", async () => {
    const element = await mount(SUPER_BASS);

    expect(element.shadowRoot!.querySelector(".hint")!.textContent).toContain("own copy");
    expect(element.shadowRoot!.querySelector(".name input")).toBeNull();
    expect(element.shadowRoot!.querySelector(".delete")).toBeNull();
  });

  it("renames an EQ of the person's own, and ignores an empty name", async () => {
    const element = await mount(MINE);
    const renames = collect<{ name: string }>(element, "rename-equalizer");
    const input = element.shadowRoot!.querySelector(".name input") as HTMLInputElement;

    input.value = "   ";
    input.dispatchEvent(new Event("change"));
    input.value = " Night drive ";
    input.dispatchEvent(new Event("change"));

    expect(renames).toEqual([{ name: "Night drive" }]);
  });

  it("asks to delete an EQ of the person's own", async () => {
    const element = await mount(MINE);
    const deletes = collect<{ id: number }>(element, "delete-equalizer");

    (element.shadowRoot!.querySelector(".delete") as HTMLButtonElement).click();

    expect(deletes).toEqual([{ id: 7 }]);
  });

  describe("undo", () => {
    function undoButton(element: EqualizerEditor): HTMLButtonElement {
      return element.shadowRoot!.querySelector(".undo") as HTMLButtonElement;
    }

    async function edit(element: EqualizerEditor, changes: { band: number; value: number }[]): Promise<void> {
      chart(element).dispatchEvent(new CustomEvent("gain-edit-start"));
      for (const change of changes) {
        chart(element).dispatchEvent(new CustomEvent("gain-change", { detail: change }));
        // app-root saves each change and hands the new curve back.
        element.equalizer = {
          ...element.equalizer!,
          gains: element.equalizer!.gains.map((gain, band) => (band === change.band ? change.value : gain)),
        };
        await element.updateComplete;
      }
    }

    it("has nothing to undo before an edit", async () => {
      const element = await mount(MINE);

      expect(undoButton(element).disabled).toBe(true);
    });

    it("takes a whole drag back in one step", async () => {
      const element = await mount(MINE);
      await edit(element, [
        { band: 6, value: -4 },
        { band: 6, value: -8 },
        { band: 6, value: -12 },
      ]);
      const changes = collect<{ gains: number[] }>(element, "equalizer-gains");

      undoButton(element).click();
      await element.updateComplete;

      expect(changes).toEqual([{ gains: MINE.gains }]);
      expect(undoButton(element).disabled).toBe(true);
    });

    it("goes back one step at a time", async () => {
      const element = await mount(MINE);
      await edit(element, [{ band: 1, value: 2 }]);
      await edit(element, [{ band: 2, value: 3 }]);
      const changes = collect<{ gains: number[] }>(element, "equalizer-gains");

      undoButton(element).click();
      await element.updateComplete;

      expect(changes.at(-1)!.gains[1]).toBe(2);
      expect(changes.at(-1)!.gains[2]).toBe(0);
      expect(undoButton(element).disabled).toBe(false);
    });

    it("forgets the steps when another EQ comes in", async () => {
      const element = await mount(MINE);
      await edit(element, [{ band: 1, value: 2 }]);

      element.equalizer = { ...MINE, id: 8, name: "Other" };
      await element.updateComplete;

      expect(undoButton(element).disabled).toBe(true);
    });

    it("keeps the steps while a factory EQ's edit becomes its copy", async () => {
      const element = await mount(SUPER_BASS);
      chart(element).dispatchEvent(new CustomEvent("gain-edit-start"));
      chart(element).dispatchEvent(new CustomEvent("gain-change", { detail: { band: 0, value: 0 } }));
      element.equalizer = { ...SUPER_BASS, id: -1, source: "custom", gains: [0, ...SUPER_BASS.gains.slice(1)] };
      await element.updateComplete;
      element.equalizer = { ...element.equalizer, id: 21 };
      await element.updateComplete;
      const changes = collect<{ gains: number[] }>(element, "equalizer-gains");

      undoButton(element).click();

      expect(changes).toEqual([{ gains: SUPER_BASS.gains }]);
    });
  });
});
