import { describe, expect, it } from "vitest";
import "./equalizer-editor.ts";
import type { EqualizerEditor } from "./equalizer-editor.ts";
import type { EqualizerDto } from "../dto/profile.dto.ts";

const MINE: EqualizerDto = { id: 7, name: "Mine", source: "custom", gains: new Array(13).fill(0) };

async function mount(): Promise<EqualizerEditor> {
  const element = document.createElement("equalizer-editor") as EqualizerEditor;
  element.equalizer = MINE;
  document.body.append(element);
  await element.updateComplete;
  return element;
}

function collect<T>(element: EqualizerEditor, type: string): T[] {
  const details: T[] = [];
  element.addEventListener(type, (rawEvent) => details.push((rawEvent as CustomEvent<T>).detail));
  return details;
}

function nameInput(element: EqualizerEditor): HTMLInputElement {
  return element.shadowRoot!.querySelector(".name input") as HTMLInputElement;
}

describe("equalizer-editor", () => {
  it("draws the EQ's curve, with no factory curve behind it", async () => {
    const element = await mount();
    const chart = element.shadowRoot!.querySelector("eq-editor")!;

    expect(chart.gains).toEqual(MINE.gains);
    expect(chart.factoryGains).toEqual([]);
  });

  it("turns a band change into the whole new curve", async () => {
    const element = await mount();
    const changes = collect<{ id: number; gains: number[] }>(element, "equalizer-change");

    element.shadowRoot!.querySelector("eq-editor")!.dispatchEvent(
      new CustomEvent("gain-change", { detail: { band: 2, value: 4.5 } }),
    );

    expect(changes).toHaveLength(1);
    expect(changes[0].id).toBe(7);
    expect(changes[0].gains[2]).toBe(4.5);
    expect(changes[0].gains.filter((gain) => gain !== 0)).toEqual([4.5]);
  });

  it("renames on a change of the name field, and ignores an empty name", async () => {
    const element = await mount();
    const changes = collect<{ id: number; name: string }>(element, "equalizer-change");
    const input = nameInput(element);

    input.value = "   ";
    input.dispatchEvent(new Event("change"));
    input.value = " Night drive ";
    input.dispatchEvent(new Event("change"));

    expect(changes).toEqual([{ id: 7, name: "Night drive" }]);
  });

  it("asks to delete the EQ, and to close the editor", async () => {
    const element = await mount();
    const deletes = collect<{ id: number }>(element, "delete-equalizer");
    const closes = collect<object>(element, "close-editor");

    (element.shadowRoot!.querySelector(".delete") as HTMLButtonElement).click();
    (element.shadowRoot!.querySelector(".done") as HTMLButtonElement).click();

    expect(deletes).toEqual([{ id: 7 }]);
    expect(closes).toHaveLength(1);
  });
});
