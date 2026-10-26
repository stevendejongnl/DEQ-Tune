import { describe, expect, it } from "vitest";
import "./crossover-panel.ts";
import { formatCutoff, type CrossoverPanel } from "./crossover-panel.ts";
import { FakeCrossoverApi } from "./testing/fake-crossover-api.ts";

async function mount(api: FakeCrossoverApi, connected = true): Promise<CrossoverPanel> {
  const element = document.createElement("crossover-panel") as CrossoverPanel;
  element.api = api;
  element.connected = connected;
  document.body.append(element);
  await element.updateComplete;
  await element.load();
  await element.updateComplete;
  return element;
}

function shadow(element: CrossoverPanel): ShadowRoot {
  return element.shadowRoot!;
}

function row(element: CrossoverPanel, speaker: string): HTMLElement {
  return shadow(element).querySelector(`li[data-speaker="${speaker}"]`)!;
}

describe("crossover-panel", () => {
  it("asks for the DEQ when no unit is connected", async () => {
    const element = await mount(new FakeCrossoverApi(), false);

    expect(shadow(element).textContent).toContain("Connect the DEQ");
    expect(shadow(element).querySelector("ul.filters")).toBeNull();
  });

  it("shows the profile's filters as values, and no select for them", async () => {
    const element = await mount(new FakeCrossoverApi());

    const rear = row(element, "rear");
    expect(rear.textContent).toContain("200 Hz · 12 dB/oct");
    expect(rear.textContent).toContain("Set by the car profile");
    expect(rear.querySelector("select")).toBeNull();
    expect(row(element, "front").textContent).toContain("Off");
  });

  it("offers the subwoofer's low pass with its stored values selected", async () => {
    const element = await mount(new FakeCrossoverApi());

    const subwoofer = row(element, "subwoofer");
    expect(subwoofer.textContent).toContain("Low pass");
    const cutoff = subwoofer.querySelector<HTMLSelectElement>('select[name="cutoff"]')!;
    const slope = subwoofer.querySelector<HTMLSelectElement>('select[name="slope"]')!;
    expect(cutoff.selectedOptions[0].textContent!.trim()).toBe("50 Hz");
    expect(slope.selectedOptions[0].textContent!.trim()).toBe("24 dB/oct");
  });

  it("sends a new cutoff and keeps the slope", async () => {
    const api = new FakeCrossoverApi();
    const element = await mount(api);
    const subwoofer = api.crossover.filters[2];

    await element.change(subwoofer, { cutoff_position: 5 });
    await element.updateComplete;

    expect(api.writes).toEqual([{ speaker: "subwoofer", cutoff_position: 5, slope: 4 }]);
    const cutoff = row(element, "subwoofer").querySelector<HTMLSelectElement>('select[name="cutoff"]')!;
    expect(cutoff.selectedOptions[0].textContent!.trim()).toBe("80 Hz");
  });

  it("says so when the unit refuses a change", async () => {
    const api = new FakeCrossoverApi();
    const element = await mount(api);
    api.failWith = 503;

    await element.change(api.crossover.filters[2], { slope: 2 });
    await element.updateComplete;

    expect(shadow(element).querySelector(".message")!.textContent).toContain("did not take");
  });

  it("names a speaker mode it cannot show", async () => {
    const api = new FakeCrossoverApi();
    api.failWith = 409;

    const element = await mount(api);

    expect(shadow(element).textContent).toContain("cannot show the filters");
  });

  it("shows the unit's speaker mode by name", async () => {
    const element = await mount(new FakeCrossoverApi());

    const select = shadow(element).querySelector<HTMLSelectElement>('select[name="speaker-mode"]')!;
    expect(select.selectedOptions[0].textContent!.trim()).toBe("Front, rear and subwoofer");
    expect(select.options).toHaveLength(5);
  });

  it("moves to front and rear, and the subwoofer row goes", async () => {
    const api = new FakeCrossoverApi();
    const element = await mount(api);

    await element.changeMode("STANDARD_FL_FR_RL_RR");
    await element.updateComplete;

    expect(api.modeChanges).toEqual(["STANDARD_FL_FR_RL_RR"]);
    expect(row(element, "subwoofer")).toBeNull();
    expect(row(element, "rear")).not.toBeNull();
  });

  it("sends nothing for the mode it already has", async () => {
    const api = new FakeCrossoverApi();
    const element = await mount(api);

    await element.changeMode("STANDARD_FL_FR_RL_RR_SW");

    expect(api.modeChanges).toEqual([]);
  });

  it("writes kilohertz for a high cutoff", () => {
    expect(formatCutoff(3150)).toBe("3.15 kHz");
    expect(formatCutoff(31.5)).toBe("31.5 Hz");
  });
});
