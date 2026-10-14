import { describe, expect, it } from "vitest";
import "./dsp-panel.ts";
import type { DspPanel } from "./dsp-panel.ts";
import type { EqualizerDto } from "../dto/profile.dto.ts";
import { LIVE_SIMULATION_IDS, liveSimulationHasNoPioneerTranslation } from "../i18n/dsp-presets.ts";

const SHOWN_LIVE_SIMULATION_IDS = LIVE_SIMULATION_IDS.filter(
  (id) => !liveSimulationHasNoPioneerTranslation(id),
);

const LIBRARY: EqualizerDto[] = [
  { id: 1, name: "Flat", source: "factory", gains: new Array(13).fill(0) },
  { id: 2, name: "Powerful", source: "factory", gains: new Array(13).fill(4) },
  { id: 3, name: "Dutch hardcore", source: "custom", gains: new Array(13).fill(2) },
];

async function mount(...active: [number | null | undefined] | []): Promise<DspPanel> {
  const activeEqualizerId = active.length === 0 ? null : active[0];
  const element = document.createElement("dsp-panel") as DspPanel;
  element.equalizers = LIBRARY;
  element.activeEqualizerId = activeEqualizerId;
  element.liveSimulationIds = LIVE_SIMULATION_IDS;
  document.body.append(element);
  await element.updateComplete;
  return element;
}

function tiles(element: DspPanel): HTMLButtonElement[] {
  return [...element.shadowRoot!.querySelectorAll(".tile")] as HTMLButtonElement[];
}

function collect<T>(element: DspPanel, type: string): T[] {
  const details: T[] = [];
  element.addEventListener(type, (rawEvent) => details.push((rawEvent as CustomEvent<T>).detail));
  return details;
}

describe("dsp-panel", () => {
  it("offers No EQ and one tile per EQ in the library", async () => {
    const element = await mount();

    expect(tiles(element).map((tile) => tile.textContent?.trim())).toEqual([
      "No EQ",
      "FLAT",
      "Powerful",
      "Dutch hardcore",
    ]);
  });

  it("marks the EQ that plays", async () => {
    const element = await mount(2);

    expect(tiles(element).map((tile) => tile.getAttribute("aria-pressed"))).toEqual([
      "false",
      "false",
      "true",
      "false",
    ]);
  });

  it("marks No EQ when none plays, and nothing before the backend answered", async () => {
    expect(tiles(await mount(null))[0].getAttribute("aria-pressed")).toBe("true");
    const unknown = await mount(undefined);
    expect(tiles(unknown).some((tile) => tile.getAttribute("aria-pressed") === "true")).toBe(false);
  });

  it("emits activate-equalizer with the tapped EQ, and null for No EQ", async () => {
    const element = await mount();
    const picks = collect<{ id: number | null }>(element, "activate-equalizer");

    tiles(element)[3].click();
    tiles(element)[0].click();

    expect(picks).toEqual([{ id: 3 }, { id: null }]);
  });

  it("offers a copy of a factory EQ, because a factory EQ is read-only", async () => {
    const element = await mount(2);
    const copies = collect<{ id: number }>(element, "copy-equalizer");

    const action = element.shadowRoot!.querySelector(".equalizer-action") as HTMLButtonElement;
    action.click();

    expect(action.textContent).toContain("Copy to edit");
    expect(copies).toEqual([{ id: 2 }]);
  });

  it("offers the editor for an EQ of the person's own", async () => {
    const element = await mount(3);
    const edits = collect<{ id: number }>(element, "edit-equalizer");

    (element.shadowRoot!.querySelector(".equalizer-action") as HTMLButtonElement).click();

    expect(edits).toEqual([{ id: 3 }]);
  });

  it("offers no action while No EQ plays", async () => {
    const element = await mount(null);
    expect(element.shadowRoot!.querySelector(".equalizer-action")).toBeNull();
  });

  it("renders one option per Live Simulation mode the real app shows", async () => {
    const element = await mount();
    expect(element.shadowRoot!.querySelectorAll(".option")).toHaveLength(
      SHOWN_LIVE_SIMULATION_IDS.length,
    );
  });

  it("leaves out the live simulation modes Pioneer never shipped a label for", async () => {
    const element = await mount();
    const options = [...element.shadowRoot!.querySelectorAll(".option")].map((option) =>
      option.textContent?.trim(),
    );
    expect(options).not.toContain("Movie");
    expect(options).not.toContain("DJ Dance Party");
  });

  it("emits live-simulation-change with the clicked option's id", async () => {
    const element = await mount();
    const changes = collect<{ id: string }>(element, "live-simulation-change");

    (element.shadowRoot!.querySelectorAll(".option")[1] as HTMLButtonElement).click();

    expect(changes).toEqual([{ id: SHOWN_LIVE_SIMULATION_IDS[1] }]);
  });

  it("translates the factory EQ names and the options for the given locale", async () => {
    const element = await mount();
    element.locale = "de";
    await element.updateComplete;

    expect(tiles(element)[2].textContent).toContain("KRAFTVOLL");
    expect(tiles(element)[3].textContent).toContain("Dutch hardcore");
    expect(element.shadowRoot!.textContent).toContain("Konzerthalle");
  });
});
