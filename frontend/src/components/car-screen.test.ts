import { afterEach, describe, expect, it } from "vitest";
import "./car-screen.ts";
import { VOLUME_STEP_DB, type CarScreen } from "./car-screen.ts";
import { sampleProfile } from "../dto/testing/sample-profile.ts";
import type { ActiveProfileDto, AudioStateDto, EqualizerDto } from "../dto/profile.dto.ts";

const EQUALIZERS: EqualizerDto[] = [
  { id: 1, name: "Super Bass", source: "factory", favorite: true, gains: new Array(13).fill(4) },
  { id: 2, name: "Mine", source: "custom", favorite: false, gains: new Array(13).fill(0) },
  { id: 3, name: "Unstarred", source: "factory", favorite: false, gains: new Array(13).fill(0) },
];

const PROFILES = [
  sampleProfile({ id: 1, name: "Mine", source: "custom", car_model: null, speaker_type: null }),
  sampleProfile({ id: 2, favorite: true }),
  sampleProfile({ id: 3, favorite: false }),
];

function active(overrides: Partial<ActiveProfileDto> = {}): ActiveProfileDto {
  return { profile_id: 1, status: "applied", problem: null, equalizer_id: null, source_mode: "STAND_ALONE", ...overrides };
}

function audio(overrides: Partial<AudioStateDto> = {}): AudioStateDto {
  return {
    source_mode: "STAND_ALONE",
    source_mode_wire: 0,
    volume_db: -20,
    muted: false,
    mute_state_wire: 0,
    driving: false,
    ...overrides,
  };
}

async function mount(setup: (element: CarScreen) => void = () => {}): Promise<CarScreen> {
  const element = document.createElement("car-screen") as CarScreen;
  element.profiles = PROFILES;
  element.equalizers = EQUALIZERS;
  element.activeProfile = active();
  setup(element);
  document.body.append(element);
  await element.updateComplete;
  return element;
}

function query<Found extends Element = HTMLButtonElement>(element: CarScreen, selector: string): Found | null {
  return element.shadowRoot!.querySelector<Found>(selector);
}

async function openTab(element: CarScreen, tab: string): Promise<void> {
  query(element, `.tab[data-tab="${tab}"]`)!.click();
  await element.updateComplete;
}

/** Collects one event type's details as the element sends them. */
function record<Detail>(element: CarScreen, type: string): Detail[] {
  const details: Detail[] = [];
  element.addEventListener(type, (event) => details.push((event as CustomEvent<Detail>).detail));
  return details;
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("car-screen", () => {
  it("offers the person's own and the starred car profiles, and marks the active one", async () => {
    const element = await mount();

    const tiles = [...element.shadowRoot!.querySelectorAll<HTMLButtonElement>(".tile")];
    expect(tiles.map((tile) => tile.dataset.profile)).toEqual(["1", "2"]);
    expect(tiles[0].getAttribute("aria-pressed")).toBe("true");
  });

  it("asks for a star when no car profile qualifies", async () => {
    const element = await mount((screen) => (screen.profiles = [sampleProfile({ id: 3 })]));

    expect(query(element, ".empty")!.textContent).toContain("Star a car profile");
  });

  it("sends the tapped car profile, and shows its loader while it waits", async () => {
    const element = await mount();
    const activations = record<{ id: number }>(element, "activate-profile");

    query(element, '.tile[data-profile="2"]')!.click();
    element.activatingProfile = true;
    await element.updateComplete;

    expect(activations).toEqual([{ id: 2 }]);
    expect(query(element, '.tile[data-profile="2"]')!.getAttribute("aria-busy")).toBe("true");
    expect(query(element, '.tile[data-profile="1"]')!.getAttribute("aria-busy")).toBe("false");
  });

  it("offers No EQ, the starred EQs and the person's own", async () => {
    const element = await mount();
    await openTab(element, "equalizers");

    const tiles = [...element.shadowRoot!.querySelectorAll<HTMLButtonElement>(".tile")];
    expect(tiles.map((tile) => tile.dataset.equalizer)).toEqual(["none", "1", "2"]);
    expect(tiles[0].getAttribute("aria-pressed")).toBe("true");
    expect(tiles[1].querySelector("svg.curve")).not.toBeNull();
  });

  it("sends the tapped EQ, and null for No EQ", async () => {
    const element = await mount((screen) => (screen.activeProfile = active({ equalizer_id: 1 })));
    const activations = record<{ id: number | null }>(element, "activate-equalizer");
    await openTab(element, "equalizers");

    query(element, '.tile[data-equalizer="2"]')!.click();
    query(element, '.tile[data-equalizer="none"]')!.click();

    expect(activations).toEqual([{ id: 2 }, { id: null }]);
  });

  it("names the car profile and the EQ that play", async () => {
    const element = await mount((screen) => (screen.activeProfile = active({ equalizer_id: 1 })));

    expect(query(element, ".now-profile")!.textContent).toBe("Mine");
    expect(query(element, ".now-equalizer")!.textContent).toBe("Super Bass");
  });

  it("steps the volume by one step each way", async () => {
    const element = await mount((screen) => {
      screen.connected = true;
      screen.audioState = audio({ volume_db: -20 });
    });
    const volumes = record<{ volumeDb: number }>(element, "volume-change");
    await openTab(element, "audio");

    const [down, up] = element.shadowRoot!.querySelectorAll<HTMLButtonElement>(".step");
    down.click();
    up.click();

    expect(volumes).toEqual([{ volumeDb: -20 - VOLUME_STEP_DB }, { volumeDb: -20 + VOLUME_STEP_DB }]);
  });

  it("turns the mute over, and shows what the unit holds", async () => {
    const element = await mount((screen) => {
      screen.connected = true;
      screen.audioState = audio({ muted: true, mute_state_wire: 1 });
    });
    const mutes = record<{ muted: boolean }>(element, "mute-change");
    await openTab(element, "audio");

    const mute = query(element, ".mute")!;
    expect(mute.getAttribute("aria-pressed")).toBe("true");
    expect(mute.textContent!.trim()).toBe("Muted");
    mute.click();

    expect(mutes).toEqual([{ muted: false }]);
  });

  it("asks for the DEQ on the audio tab while no unit is linked", async () => {
    const element = await mount();
    await openTab(element, "audio");

    expect(query(element, ".step")).toBeNull();
    expect(query(element, ".empty")!.textContent).toContain("Connect the DEQ");
  });

  it("has no way to the full app", async () => {
    const element = await mount();

    expect(query(element, ".full-app")).toBeNull();
  });

  it("names the tab that opens", async () => {
    const element = await mount();
    const tabs = record<{ tab: string }>(element, "tab-change");

    await openTab(element, "audio");

    expect(tabs).toEqual([{ tab: "audio" }]);
  });
});
