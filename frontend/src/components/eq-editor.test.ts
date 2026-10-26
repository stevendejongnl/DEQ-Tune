import { describe, expect, it } from "vitest";
import "./eq-editor.ts";
import { pointerInChart, type EqEditor } from "./eq-editor.ts";
import { EQ_BAND_FREQUENCIES } from "../eq-bands.ts";
import type { AppLayout } from "../layout-query.ts";

const FLAT = new Array(13).fill(0);

async function mount(
  gains: number[],
  factoryGains: number[] = [],
  layout: AppLayout = "desktop",
): Promise<EqEditor> {
  const element = document.createElement("eq-editor") as EqEditor;
  element.gains = gains;
  element.factoryGains = factoryGains;
  element.layout = layout;
  document.body.append(element);
  await element.updateComplete;
  return element;
}

function queryBandButtons(element: EqEditor): NodeListOf<HTMLButtonElement> {
  return element.shadowRoot!.querySelectorAll(".band-hit");
}

function queryChartFrame(element: EqEditor): HTMLElement {
  return element.shadowRoot!.querySelector(".chart-frame") as HTMLElement;
}

/** The x of a band on the desktop chart at its fallback width of 640:
 * 36 px of left padding, 16 px of right padding, and a log axis. */
function bandCentreX(band: number): number {
  return 36 + (Math.log(EQ_BAND_FREQUENCIES[band] / 50) / Math.log(250)) * (640 - 36 - 16);
}

/** The same on the phone chart at 358 wide, with 30 and 10 of padding. */
function phoneBandCentreX(band: number): number {
  return 30 + (Math.log(EQ_BAND_FREQUENCIES[band] / 50) / Math.log(250)) * (358 - 30 - 10);
}

/** Presses the chart at (x, y), moves to each y in turn, and lets go.
 * jsdom puts the chart at the page origin, so client and chart
 * coordinates agree. */
function drag(element: EqEditor, x: number, startY: number, moveYs: readonly number[]): void {
  const frame = queryChartFrame(element);
  const pointer = { pointerId: 1, bubbles: true, clientX: x };
  frame.dispatchEvent(new PointerEvent("pointerdown", { ...pointer, clientY: startY }));
  for (const y of moveYs) {
    frame.dispatchEvent(new PointerEvent("pointermove", { ...pointer, clientY: y }));
  }
  frame.dispatchEvent(new PointerEvent("pointerup", pointer));
}

function collectGains(element: EqEditor): { band: number; value: number }[] {
  const changes: { band: number; value: number }[] = [];
  element.addEventListener("gain-change", (rawEvent) => {
    changes.push((rawEvent as CustomEvent).detail);
  });
  return changes;
}

async function click(element: EqEditor, button: HTMLElement): Promise<void> {
  button.dispatchEvent(new Event("click"));
  await element.updateComplete;
}

describe("eq-editor", () => {
  it("draws one hit target per EQ band", async () => {
    const element = await mount([...FLAT]);
    expect(queryBandButtons(element)).toHaveLength(EQ_BAND_FREQUENCIES.length);
  });

  it("draws your curve and the factory curve when factory gains are given", async () => {
    const element = await mount([...FLAT], [...FLAT]);
    expect(element.shadowRoot!.querySelector(".curve")).not.toBeNull();
    expect(element.shadowRoot!.querySelector(".factory-curve")).not.toBeNull();
  });

  it("draws no factory curve when no factory gains are given", async () => {
    const element = await mount([...FLAT]);
    expect(element.shadowRoot!.querySelector(".factory-curve")).toBeNull();
  });

  it("starts on the highest band", async () => {
    const element = await mount([...FLAT]);
    const selected = element.shadowRoot!.querySelector('.band-hit[aria-pressed="true"]');
    expect(selected!.getAttribute("aria-label")).toContain("12.5 kHz");
  });

  it("names each band with its frequency and its gain", async () => {
    const element = await mount([3.5, ...new Array(12).fill(0)]);
    expect(queryBandButtons(element)[0].getAttribute("aria-label")).toBe("50 Hz, +3.5 dB");
  });

  it("emits gain-change with the clamped value from the stepper", async () => {
    const element = await mount([...FLAT]);
    let detail: { band: number; value: number } | undefined;
    element.addEventListener("gain-change", (rawEvent) => {
      detail = (rawEvent as CustomEvent).detail;
    });

    const raise = element.shadowRoot!.querySelectorAll(".step")[1] as HTMLButtonElement;
    await click(element, raise);

    expect(detail).toEqual({ band: 12, value: 0.5 });
  });

  it("emits gain-change from the range input", async () => {
    const element = await mount([...FLAT]);
    let detail: { band: number; value: number } | undefined;
    element.addEventListener("gain-change", (rawEvent) => {
      detail = (rawEvent as CustomEvent).detail;
    });

    const slider = element.shadowRoot!.querySelector('input[type="range"]') as HTMLInputElement;
    slider.value = "6";
    slider.dispatchEvent(new Event("input"));

    expect(detail).toEqual({ band: 12, value: 6 });
  });

  it("selects the first band of a zone when its zone button is pressed", async () => {
    const element = await mount([...FLAT]);

    const zones = element.shadowRoot!.querySelectorAll(".zone");
    await click(element, zones[0] as HTMLElement);

    const selected = element.shadowRoot!.querySelector('.band-hit[aria-pressed="true"]');
    expect(selected!.getAttribute("aria-label")).toContain("50 Hz");
  });

  it("moves the selection with the left and right keys", async () => {
    const element = await mount([...FLAT]);

    const bands = queryBandButtons(element);
    bands[12].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft" }));
    await element.updateComplete;

    const selected = element.shadowRoot!.querySelector('.band-hit[aria-pressed="true"]');
    expect(selected!.getAttribute("aria-label")).toContain("8 kHz");
  });

  it("changes the gain with the up and down keys", async () => {
    const element = await mount([...FLAT]);
    let detail: { band: number; value: number } | undefined;
    element.addEventListener("gain-change", (rawEvent) => {
      detail = (rawEvent as CustomEvent).detail;
    });

    queryBandButtons(element)[12].dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowUp" }));

    expect(detail).toEqual({ band: 12, value: 0.5 });
  });

  it("offers a reset for a band that differs from factory", async () => {
    const gains = [...FLAT];
    gains[12] = 6;
    const element = await mount(gains, [...FLAT]);
    let detail: { band: number; value: number } | undefined;
    element.addEventListener("gain-change", (rawEvent) => {
      detail = (rawEvent as CustomEvent).detail;
    });

    const reset = element.shadowRoot!.querySelector(".reset-band") as HTMLButtonElement;
    await click(element, reset);

    expect(detail).toEqual({ band: 12, value: 0 });
  });

  it("hides the reset when the band matches factory", async () => {
    const element = await mount([...FLAT], [...FLAT]);
    expect(element.shadowRoot!.querySelector(".reset-band")).toBeNull();
  });

  it("changes the gain while a dot is dragged", async () => {
    const element = await mount([...FLAT], [...FLAT]);
    const gains = collectGains(element);

    // The chart is 300 tall with 24 padding, so 0 dB sits at y 150 and
    // the top edge, +12 dB, at y 24.
    drag(element, bandCentreX(6), 150, [24]);

    expect(gains.at(-1)).toEqual({ band: 6, value: 12 });
  });

  it("keeps the grab offset, so the dot does not jump to the pointer", async () => {
    const element = await mount([...FLAT], [...FLAT]);
    const gains = collectGains(element);

    // A press 20 px below the dot, then a move up by 63 px, which is 6 dB
    // on a 252 px span for 24 dB.
    drag(element, bandCentreX(6), 170, [107]);

    expect(gains.at(-1)).toEqual({ band: 6, value: 6 });
  });

  it("drags the band nearest to the press, also between two dots", async () => {
    const element = await mount([...FLAT], [...FLAT]);
    const gains = collectGains(element);

    drag(element, bandCentreX(2) + 3, 150, [24]);

    expect(gains.at(-1)?.band).toBe(2);
  });

  it("sends nothing for a move inside one 0.5 dB step", async () => {
    const element = await mount([...FLAT], [...FLAT]);
    const gains = collectGains(element);

    drag(element, bandCentreX(6), 150, [149, 148]);

    expect(gains).toHaveLength(0);
  });

  it("ignores pointer moves when no band is held", async () => {
    const element = await mount([...FLAT], [...FLAT]);
    const gains = collectGains(element);

    queryChartFrame(element).dispatchEvent(
      new PointerEvent("pointermove", { pointerId: 1, clientY: 24, bubbles: true }),
    );

    expect(gains).toHaveLength(0);
  });

  it("lets a touch swipe over the chart scroll, and moves no band", async () => {
    const element = await mount([...FLAT], [...FLAT], "phone");
    const gains = collectGains(element);
    const frame = queryChartFrame(element);
    const touch = { pointerId: 1, pointerType: "touch", bubbles: true, clientX: phoneBandCentreX(4) };

    frame.dispatchEvent(new PointerEvent("pointerdown", { ...touch, clientY: 110 }));
    frame.dispatchEvent(new PointerEvent("pointermove", { ...touch, clientY: 16 }));
    frame.dispatchEvent(new PointerEvent("pointerup", touch));

    expect(gains).toHaveLength(0);
  });

  it("drags a band by touch from its dot's handle", async () => {
    const element = await mount([...FLAT], [...FLAT], "phone");
    const gains = collectGains(element);
    const frame = queryChartFrame(element);
    const handle = element.shadowRoot!.querySelectorAll<HTMLElement>(".handle")[4];
    const touch = { pointerId: 1, pointerType: "touch", bubbles: true, clientX: phoneBandCentreX(4) };

    handle.dispatchEvent(new PointerEvent("pointerdown", { ...touch, clientY: 110 }));
    frame.dispatchEvent(new PointerEvent("pointermove", { ...touch, clientY: 16 }));
    frame.dispatchEvent(new PointerEvent("pointerup", touch));

    expect(gains.at(-1)).toEqual({ band: 4, value: 12 });
  });

  it("starts an edit step for each drag and each tap on − or +", async () => {
    const element = await mount([...FLAT]);
    let starts = 0;
    element.addEventListener("gain-edit-start", () => (starts += 1));

    drag(element, bandCentreX(6), 150, [24, 30]);
    await element.updateComplete;
    const raise = element.shadowRoot!.querySelectorAll<HTMLButtonElement>(".step")[1];
    await click(element, raise);
    await click(element, raise);

    expect(starts).toBe(3);
  });

  it("drags on the phone too, where the dots are too small to hit", async () => {
    const element = await mount([...FLAT], [...FLAT], "phone");
    const gains = collectGains(element);

    // The phone chart is 220 tall with 16 padding: 0 dB at y 110, +12 at 16.
    drag(element, phoneBandCentreX(4), 110, [16]);

    expect(gains.at(-1)).toEqual({ band: 4, value: 12 });
  });

  it("shows band chips instead of zones in the phone layout", async () => {
    const element = await mount([...FLAT], [...FLAT], "phone");

    expect(element.shadowRoot!.querySelectorAll(".chip")).toHaveLength(
      EQ_BAND_FREQUENCIES.length,
    );
    expect(element.shadowRoot!.querySelector(".zone")).toBeNull();
    expect(element.shadowRoot!.querySelector(".band-hit")).toBeNull();
  });

  it("selects a band from its phone chip", async () => {
    const element = await mount([...FLAT], [...FLAT], "phone");

    const chips = element.shadowRoot!.querySelectorAll(".chip");
    await click(element, chips[3] as HTMLElement);

    expect(chips[3].getAttribute("aria-pressed")).toBe("true");
  });
});

describe("pointerInChart", () => {
  it("turns screen pixels into chart pixels under CSS zoom", () => {
    const frame = document.createElement("div");
    frame.getBoundingClientRect = () => new DOMRect(100, 50, 744, 360);
    Object.defineProperty(frame, "currentCSSZoom", { value: 1.2 });

    const point = pointerInChart(new MouseEvent("pointermove", { clientX: 220, clientY: 170 }), frame);

    expect(point.x).toBeCloseTo(100);
    expect(point.y).toBeCloseTo(100);
  });

  it("leaves the pixels alone with no zoom", () => {
    const frame = document.createElement("div");
    frame.getBoundingClientRect = () => new DOMRect(10, 20, 620, 300);

    expect(pointerInChart(new MouseEvent("pointermove", { clientX: 40, clientY: 70 }), frame)).toEqual({ x: 30, y: 50 });
  });
});
