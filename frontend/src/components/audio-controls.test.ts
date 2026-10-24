import { afterEach, describe, expect, it } from "vitest";
import type { AudioStateDto } from "../dto/profile.dto.ts";
import "./audio-controls.ts";
import { VOLUME_SEND_DELAY_MS, type AudioControls } from "./audio-controls.ts";

function audioState(volumeDb: number): AudioStateDto {
  return {
    source_mode: "CAR_SOURCE",
    source_mode_wire: 1,
    volume_db: volumeDb,
    muted: false,
    mute_state_wire: 0,
    driving: false,
  };
}

/** Holds the panel's delayed send instead of running it. A test fires it. */
class ManualSchedule {
  delays: number[] = [];
  private pending: (() => void) | null = null;

  schedule = (action: () => void, delayMs: number): unknown => {
    this.delays.push(delayMs);
    this.pending = action;
    return this.delays.length;
  };

  cancel = (): void => {
    this.pending = null;
  };

  fire(): void {
    const action = this.pending;
    this.pending = null;
    action?.();
  }
}

type Mounted = { element: AudioControls; schedule: ManualSchedule; sent: number[] };

async function mount(volumeDb = -17): Promise<Mounted> {
  const schedule = new ManualSchedule();
  const sent: number[] = [];
  const element = document.createElement("audio-controls") as AudioControls;
  element.state = audioState(volumeDb);
  element.connected = true;
  element.sourceNames = ["CAR_SOURCE", "THROUGH"];
  element.scheduleFunction = schedule.schedule;
  element.cancelFunction = schedule.cancel;
  element.addEventListener("volume-change", (event) =>
    sent.push((event as CustomEvent<{ volumeDb: number }>).detail.volumeDb),
  );
  document.body.append(element);
  await element.updateComplete;
  return { element, schedule, sent };
}

function slider(element: AudioControls): HTMLInputElement {
  return element.shadowRoot!.querySelector<HTMLInputElement>('input[type="range"]')!;
}

function readout(element: AudioControls): string {
  return element.shadowRoot!.querySelector(".volume-readout")!.textContent!.replace(/\s+/g, " ").trim();
}

async function drag(element: AudioControls, volumeDb: number): Promise<void> {
  slider(element).value = String(volumeDb);
  slider(element).dispatchEvent(new Event("input"));
  await element.updateComplete;
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("audio-controls volume", () => {
  it("shows a drag's value at once and sends it when the slider rests", async () => {
    const { element, schedule, sent } = await mount();

    await drag(element, -12);
    await drag(element, -10);

    expect(readout(element)).toBe("-10 dB");
    expect(sent).toEqual([]);
    expect(schedule.delays.at(-1)).toBe(VOLUME_SEND_DELAY_MS);

    schedule.fire();
    expect(sent).toEqual([-10]);
  });

  it("sends at once when the finger lets go, and not twice", async () => {
    const { element, schedule, sent } = await mount();

    await drag(element, -8);
    slider(element).dispatchEvent(new Event("change"));
    schedule.fire();

    expect(sent).toEqual([-8]);
  });

  it("steps one dB with the buttons, within the unit's range", async () => {
    const { element, sent } = await mount(9);
    const [down, up] = element.shadowRoot!.querySelectorAll<HTMLButtonElement>(".step");

    up.click();
    await element.updateComplete;
    up.click();
    await element.updateComplete;
    down.click();
    await element.updateComplete;

    expect(sent).toEqual([10, 9]);
    expect(readout(element)).toBe("9 dB");
  });

  it("keeps the slider usable while a request is out", async () => {
    const { element } = await mount();
    element.busy = true;
    await element.updateComplete;

    expect(slider(element).disabled).toBe(false);
  });

  it("turns the controls off while the unit is not linked", async () => {
    const { element } = await mount();
    element.connected = false;
    await element.updateComplete;

    expect(slider(element).disabled).toBe(true);
    expect(element.shadowRoot!.querySelector<HTMLButtonElement>(".step")!.disabled).toBe(true);
  });

  it("shows the polled volume once nothing waits to send", async () => {
    const { element, schedule } = await mount();
    await drag(element, -5);
    schedule.fire();

    element.state = audioState(-5);
    await element.updateComplete;
    element.state = audioState(-20);
    await element.updateComplete;

    expect(readout(element)).toBe("-20 dB");
  });
});
