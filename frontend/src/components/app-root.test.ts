import { describe, expect, it } from "vitest";
import "./app-root.ts";
import { AUDIO_POLL_MS, type AppRoot } from "./app-root.ts";
import { FakeProfileApi } from "./testing/fake-profile-api.ts";
import { sampleProfile } from "../dto/testing/sample-profile.ts";
import { flushMicrotasks } from "../testing/flush-microtasks.ts";
import { createFakeLocaleStorage } from "../i18n/testing/fake-locale-storage.ts";
import { createFakeLayoutQuery, type FakeLayoutQuery } from "../testing/fake-layout-query.ts";
import type { AppLayout } from "../layout-query.ts";
import type { ProfileList } from "./profile-list.ts";

async function mount(api: FakeProfileApi, layout: AppLayout = "desktop"): Promise<AppRoot> {
  const element = document.createElement("app-root") as AppRoot;
  element.api = api;
  element.localeStorage = createFakeLocaleStorage({});
  element.browserLanguages = ["en-US"];
  element.layoutQuery = createFakeLayoutQuery(layout);
  document.body.append(element);
  await flushMicrotasks();
  await element.updateComplete;
  return element;
}

async function click(button: HTMLButtonElement, element: AppRoot): Promise<void> {
  button.dispatchEvent(new Event("click"));
  await flushMicrotasks();
  await element.updateComplete;
}

function queryProfileList(element: AppRoot): ProfileList {
  return element.shadowRoot!.querySelector("profile-list") as ProfileList;
}

function queryModelRows(element: AppRoot): NodeListOf<HTMLLIElement> {
  return queryProfileList(element).shadowRoot!.querySelectorAll(".model-row");
}

/** The factory rows select through their speaker chips. */
function queryFirstChip(element: AppRoot): HTMLButtonElement {
  return queryProfileList(element).shadowRoot!.querySelector(".chip") as HTMLButtonElement;
}

function queryDrawer(element: AppRoot): HTMLElement {
  return element.shadowRoot!.querySelector(".drawer") as HTMLElement;
}

function queryProfilesToggle(element: AppRoot): HTMLButtonElement {
  return element.shadowRoot!.querySelector(".profiles-toggle") as HTMLButtonElement;
}

describe("app-root", () => {
  it("saves the unit's tune as a custom profile and opens it", async () => {
    const api = new FakeProfileApi([sampleProfile({ id: 1 })]);
    api.device.startConnected();
    api.unitTuning = sampleProfile().data;
    const element = await mount(api);

    const saveButton = queryProfileList(element).shadowRoot!.querySelector(
      ".save-unit-tune",
    ) as HTMLButtonElement;
    await click(saveButton, element);

    const profiles = await api.listProfiles();
    const saved = profiles.find((profile) => profile.name === "Unit tune");
    expect(saved?.source).toBe("custom");
    expect(queryProfileList(element).selectedId).toBe(saved?.id);
  });

  it("loads and lists profiles from the injected api on connect", async () => {
    const api = new FakeProfileApi([
      sampleProfile({ id: 1, name: "Factory preset", source: "factory" }),
    ]);

    const element = await mount(api);

    expect(queryModelRows(element)).toHaveLength(1);
  });

  it("shows a prompt to select a profile before one is chosen", async () => {
    const element = await mount(new FakeProfileApi([sampleProfile({ id: 1 })]));

    expect(element.shadowRoot!.textContent).toContain("Select a profile");
  });

  it("shows the EQ editor for the selected profile", async () => {
    const api = new FakeProfileApi([
      sampleProfile({ id: 1, name: "Factory preset", source: "factory" }),
    ]);
    const element = await mount(api);

    await click(queryFirstChip(element), element);

    expect(element.shadowRoot!.querySelector("eq-editor")).not.toBeNull();
  });

  it("persists a gain change through the api for a custom profile", async () => {
    const api = new FakeProfileApi([sampleProfile({ id: 1, name: "My EQ", source: "custom" })]);
    const element = await mount(api);
    const customName = queryProfileList(element).shadowRoot!.querySelector(
      ".custom-row .name",
    ) as HTMLButtonElement;
    await click(customName, element);

    const eqEditor = element.shadowRoot!.querySelector("eq-editor")!;
    eqEditor.dispatchEvent(new CustomEvent("gain-change", { detail: { band: 2, value: 4.5 } }));
    await flushMicrotasks();
    await element.updateComplete;

    const saved = await api.getProfile(1);
    expect(saved.data.foundationEq.eqs.LR.banks[0][2]).toBe(4.5);
  });

  it("selects the new copy after a duplicate-profile event", async () => {
    const api = new FakeProfileApi([
      sampleProfile({ id: 1, name: "Factory preset", source: "factory" }),
    ]);
    const element = await mount(api);

    queryProfileList(element).dispatchEvent(
      new CustomEvent("duplicate-profile", { detail: { id: 1 } }),
    );
    await flushMicrotasks();
    await element.updateComplete;

    expect(queryProfileList(element).shadowRoot!.querySelectorAll(".custom-row")).toHaveLength(1);
  });

  it("starts in the browser's detected language when nothing is saved", async () => {
    const element = document.createElement("app-root") as AppRoot;
    element.api = new FakeProfileApi([sampleProfile({ id: 1 })]);
    element.localeStorage = createFakeLocaleStorage({});
    element.browserLanguages = ["ja-JP"];
    element.layoutQuery = createFakeLayoutQuery("desktop");
    document.body.append(element);
    await flushMicrotasks();
    await element.updateComplete;

    const profileListText = queryProfileList(element).shadowRoot!.textContent;
    expect(profileListText).toContain("純正");
  });

  it("switches language via the locale switcher and remembers the choice", async () => {
    const storage = createFakeLocaleStorage({});
    const element = document.createElement("app-root") as AppRoot;
    element.api = new FakeProfileApi([sampleProfile({ id: 1 })]);
    element.localeStorage = storage;
    element.browserLanguages = ["en-US"];
    element.layoutQuery = createFakeLayoutQuery("desktop");
    document.body.append(element);
    await flushMicrotasks();
    await element.updateComplete;

    const select = element.shadowRoot!
      .querySelector("locale-switcher")!
      .shadowRoot!.querySelector("select") as HTMLSelectElement;
    select.value = "de";
    select.dispatchEvent(new Event("change"));
    await element.updateComplete;

    const profileListText = queryProfileList(element).shadowRoot!.textContent;
    expect(profileListText).toContain("Werk");
    expect(storage.getItem("deq-tune-locale")).toBe("de");
  });

  it("starts with the profiles drawer closed", async () => {
    const element = await mount(new FakeProfileApi([sampleProfile({ id: 1 })]));

    expect(queryDrawer(element).classList.contains("open")).toBe(false);
    expect(element.shadowRoot!.querySelector(".drawer-backdrop")).toBeNull();
  });

  it("opens the profiles drawer from the header toggle", async () => {
    const element = await mount(new FakeProfileApi([sampleProfile({ id: 1 })]));

    await click(queryProfilesToggle(element), element);

    expect(queryDrawer(element).classList.contains("open")).toBe(true);
    expect(element.shadowRoot!.querySelector(".drawer-backdrop")).not.toBeNull();
  });

  it("closes the profiles drawer when the backdrop is clicked", async () => {
    const element = await mount(new FakeProfileApi([sampleProfile({ id: 1 })]));
    await click(queryProfilesToggle(element), element);

    const backdrop = element.shadowRoot!.querySelector(".drawer-backdrop") as HTMLElement;
    backdrop.dispatchEvent(new Event("click"));
    await flushMicrotasks();
    await element.updateComplete;

    expect(queryDrawer(element).classList.contains("open")).toBe(false);
  });

  it("closes the profiles drawer when Escape is pressed", async () => {
    const element = await mount(new FakeProfileApi([sampleProfile({ id: 1 })]));
    await click(queryProfilesToggle(element), element);

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await element.updateComplete;

    expect(queryDrawer(element).classList.contains("open")).toBe(false);
  });

  it("shows the brand, the speaker type and the model name above the panels", async () => {
    const element = await mount(new FakeProfileApi([sampleProfile({ id: 1 })]));

    await click(queryFirstChip(element), element);

    const heading = element.shadowRoot!.querySelector(".heading-row")!;
    expect(heading.textContent).toContain("Mazda");
    expect(heading.textContent).toContain("For Normal Speaker");
    expect(heading.querySelector(".profile-title")!.textContent).toContain("Mazda3");
  });

  it("shows every panel at once outside the phone layout", async () => {
    const element = await mount(new FakeProfileApi([sampleProfile({ id: 1 })]));
    await click(queryFirstChip(element), element);

    expect(element.shadowRoot!.querySelector(".tab-bar")).toBeNull();
    expect(element.shadowRoot!.querySelector("eq-editor")).not.toBeNull();
    expect(element.shadowRoot!.querySelector("speaker-panel")).not.toBeNull();
    expect(element.shadowRoot!.querySelector("dsp-panel")).not.toBeNull();
  });

  it("passes the unit's own EQ style and live simulation ids to the panel", async () => {
    const api = new FakeProfileApi([sampleProfile({ id: 1 })]);
    const element = await mount(api);
    await click(queryFirstChip(element), element);

    const panel = element.shadowRoot!.querySelector("dsp-panel")!;
    expect(panel.shadowRoot!.querySelectorAll(".tile")).toHaveLength(3);
    expect(panel.shadowRoot!.querySelectorAll(".option")).toHaveLength(3);
  });

  it("sends an EQ style choice to the unit, under the name the unit knows", async () => {
    const api = new FakeProfileApi([sampleProfile({ id: 1 })]);
    const element = await mount(api);
    await click(queryFirstChip(element), element);

    element.shadowRoot!.querySelector("dsp-panel")!.dispatchEvent(
      new CustomEvent("eq-style-change", { detail: { id: "SUPER_BASS" } }),
    );
    await element.updateComplete;

    expect(api.device.selectedEqStyles).toEqual(["SUPER_BASS"]);
  });

  it("sends a live simulation choice to the unit", async () => {
    const api = new FakeProfileApi([sampleProfile({ id: 1 })]);
    const element = await mount(api);
    await click(queryFirstChip(element), element);

    element.shadowRoot!.querySelector("dsp-panel")!.dispatchEvent(
      new CustomEvent("live-simulation-change", { detail: { id: "CONCERT_HALL" } }),
    );
    await element.updateComplete;

    expect(api.device.selectedLiveSimulations).toEqual(["CONCERT_HALL"]);
  });

  it("keeps the choice when the unit is not reachable", async () => {
    const api = new FakeProfileApi([sampleProfile({ id: 1 })]);
    api.device.selectEqStyle = () => Promise.reject(new Error("the unit is not connected"));
    const element = await mount(api);
    await click(queryFirstChip(element), element);

    element.shadowRoot!.querySelector("dsp-panel")!.dispatchEvent(
      new CustomEvent("eq-style-change", { detail: { id: "POWERFUL" } }),
    );
    await element.updateComplete;

    expect(element.shadowRoot!.querySelector("dsp-panel")).not.toBeNull();
  });

  it("renders only the active tab in the phone layout", async () => {
    const element = await mount(new FakeProfileApi([sampleProfile({ id: 1 })]), "phone");
    await click(queryFirstChip(element), element);
    const eqTab = element.shadowRoot!.querySelectorAll(".tab")[1] as HTMLButtonElement;
    await click(eqTab, element);

    expect(element.shadowRoot!.querySelector(".tab-bar")).not.toBeNull();
    expect(element.shadowRoot!.querySelector("eq-editor")).not.toBeNull();
    expect(element.shadowRoot!.querySelector("speaker-panel")).toBeNull();
    expect(element.shadowRoot!.querySelector("dsp-panel")).toBeNull();
  });

  it("swaps the panel when another phone tab is pressed", async () => {
    const element = await mount(new FakeProfileApi([sampleProfile({ id: 1 })]), "phone");
    await click(queryFirstChip(element), element);
    const eqTab = element.shadowRoot!.querySelectorAll(".tab")[1] as HTMLButtonElement;
    await click(eqTab, element);

    const speakersTab = element.shadowRoot!.querySelectorAll(".tab")[2] as HTMLButtonElement;
    await click(speakersTab, element);

    expect(speakersTab.getAttribute("aria-pressed")).toBe("true");
    expect(element.shadowRoot!.querySelector("speaker-panel")).not.toBeNull();
    expect(element.shadowRoot!.querySelector("eq-editor")).toBeNull();
  });

  it("edits a factory preset without saving it", async () => {
    const api = new FakeProfileApi([
      sampleProfile({ id: 1, name: "Factory preset", source: "factory" }),
    ]);
    const element = await mount(api);
    await click(queryFirstChip(element), element);

    element.shadowRoot!.querySelector("eq-editor")!.dispatchEvent(
      new CustomEvent("gain-change", { detail: { band: 2, value: 4.5 } }),
    );
    await flushMicrotasks();
    await element.updateComplete;

    const stored = await api.getProfile(1);
    expect(stored.data.foundationEq.eqs.LR.banks[0][2]).toBe(0);
    expect(element.shadowRoot!.querySelector(".badge")!.textContent).toContain("Edited · 1 band");
  });

  it("shows the neutral badge and the hint before any edit", async () => {
    const element = await mount(new FakeProfileApi([sampleProfile({ id: 1 })]));
    await click(queryFirstChip(element), element);

    expect(element.shadowRoot!.querySelector(".badge")!.textContent).toContain("Factory preset");
    expect(element.shadowRoot!.querySelector(".start-hint")).not.toBeNull();
  });

  it("counts every changed band in the badge", async () => {
    const element = await mount(new FakeProfileApi([sampleProfile({ id: 1 })]));
    await click(queryFirstChip(element), element);
    const editor = element.shadowRoot!.querySelector("eq-editor")!;

    for (const band of [0, 1, 2]) {
      editor.dispatchEvent(new CustomEvent("gain-change", { detail: { band, value: 3 } }));
      await flushMicrotasks();
      await element.updateComplete;
    }

    expect(element.shadowRoot!.querySelector(".badge")!.textContent).toContain("Edited · 3 bands");
  });

  it("reverts a draft back to the factory data", async () => {
    const element = await mount(new FakeProfileApi([sampleProfile({ id: 1 })]));
    await click(queryFirstChip(element), element);
    element.shadowRoot!.querySelector("eq-editor")!.dispatchEvent(
      new CustomEvent("gain-change", { detail: { band: 2, value: 4.5 } }),
    );
    await flushMicrotasks();
    await element.updateComplete;

    await click(element.shadowRoot!.querySelector(".secondary") as HTMLButtonElement, element);

    expect(element.shadowRoot!.querySelector(".badge")!.textContent).toContain("Factory preset");
  });

  it("saves a draft as a new profile and selects the copy", async () => {
    const api = new FakeProfileApi([
      sampleProfile({ id: 1, name: "Factory preset", source: "factory" }),
    ]);
    const element = await mount(api);
    await click(queryFirstChip(element), element);
    element.shadowRoot!.querySelector("eq-editor")!.dispatchEvent(
      new CustomEvent("gain-change", { detail: { band: 2, value: 4.5 } }),
    );
    await flushMicrotasks();
    await element.updateComplete;

    await click(element.shadowRoot!.querySelector(".primary") as HTMLButtonElement, element);
    await flushMicrotasks();
    await element.updateComplete;

    const copies = queryProfileList(element).shadowRoot!.querySelectorAll(".custom-row");
    expect(copies).toHaveLength(1);
    const saved = await api.getProfile(2);
    expect(saved.data.foundationEq.eqs.LR.banks[0][2]).toBe(4.5);
  });

  it("asks before it drops a draft for another profile", async () => {
    const element = await mount(new FakeProfileApi([sampleProfile({ id: 1 }), sampleProfile({ id: 2, car_model: "mazda_6" })]));
    const questions: string[] = [];
    element.confirmDiscard = (question) => {
      questions.push(question);
      return false;
    };
    await click(queryFirstChip(element), element);
    element.shadowRoot!.querySelector("eq-editor")!.dispatchEvent(
      new CustomEvent("gain-change", { detail: { band: 2, value: 4.5 } }),
    );
    await flushMicrotasks();
    await element.updateComplete;

    const otherChip = queryProfileList(element).shadowRoot!.querySelectorAll(".chip")[1];
    await click(otherChip as HTMLButtonElement, element);

    expect(questions).toHaveLength(1);
    expect(element.shadowRoot!.querySelector(".badge")!.textContent).toContain("Edited");
  });

  it("puts the save actions in a bar on the phone", async () => {
    const element = await mount(new FakeProfileApi([sampleProfile({ id: 1 })]), "phone");
    await click(queryFirstChip(element), element);
    const eqTab = element.shadowRoot!.querySelectorAll(".tab")[1] as HTMLButtonElement;
    await click(eqTab, element);
    expect(element.shadowRoot!.querySelector(".save-bar")).toBeNull();

    element.shadowRoot!.querySelector("eq-editor")!.dispatchEvent(
      new CustomEvent("gain-change", { detail: { band: 2, value: 4.5 } }),
    );
    await flushMicrotasks();
    await element.updateComplete;

    const saveBar = element.shadowRoot!.querySelector(".save-bar")!;
    expect(saveBar.textContent).toContain("Edited · 1 band");
    expect(saveBar.querySelector(".primary")).not.toBeNull();
  });

  it("keeps the language control in the header outside the phone layout", async () => {
    const element = await mount(new FakeProfileApi([sampleProfile({ id: 1 })]));

    expect(element.shadowRoot!.querySelector("header locale-switcher")).not.toBeNull();
    expect(element.shadowRoot!.querySelector(".drawer locale-switcher")).toBeNull();
  });

  it("moves the language control into the sheet in the phone layout", async () => {
    const element = await mount(new FakeProfileApi([sampleProfile({ id: 1 })]), "phone");

    expect(element.shadowRoot!.querySelector("header locale-switcher")).toBeNull();
    expect(element.shadowRoot!.querySelector(".drawer locale-switcher")).not.toBeNull();
  });

  it("moves to the phone layout when the viewport becomes narrow", async () => {
    const layoutQuery: FakeLayoutQuery = createFakeLayoutQuery("desktop");
    const element = document.createElement("app-root") as AppRoot;
    element.api = new FakeProfileApi([sampleProfile({ id: 1 })]);
    element.localeStorage = createFakeLocaleStorage({});
    element.browserLanguages = ["en-US"];
    element.layoutQuery = layoutQuery;
    document.body.append(element);
    await flushMicrotasks();
    await element.updateComplete;
    expect(element.shadowRoot!.querySelector(".tab-bar")).toBeNull();

    layoutQuery.setLayout("phone");
    await element.updateComplete;

    expect(element.shadowRoot!.querySelector(".tab-bar")).not.toBeNull();
  });

  it("closes the profiles drawer after selecting a profile", async () => {
    const element = await mount(new FakeProfileApi([sampleProfile({ id: 1 })]));
    await click(queryProfilesToggle(element), element);

    await click(queryFirstChip(element), element);

    expect(queryDrawer(element).classList.contains("open")).toBe(false);
  });
  describe("audio panel and the unit link", () => {
    /** Holds the one waiting timer, so a test fires it instead of sleeping. */
    class ManualSchedule {
      pending: (() => void) | null = null;
      delayMs: number | null = null;
      schedule = (action: () => void, delayMs: number): unknown => {
        this.pending = action;
        this.delayMs = delayMs;
        return 1;
      };
      cancel = (): void => {
        this.pending = null;
      };
      async fire(element: AppRoot): Promise<void> {
        const action = this.pending;
        this.pending = null;
        action?.();
        await flushMicrotasks();
        await element.updateComplete;
      }
    }

    async function mountWithSchedule(
      api: FakeProfileApi,
      schedule: ManualSchedule,
      layout: AppLayout = "desktop",
    ): Promise<AppRoot> {
      const element = document.createElement("app-root") as AppRoot;
      element.api = api;
      element.localeStorage = createFakeLocaleStorage({});
      element.browserLanguages = ["en-US"];
      element.layoutQuery = createFakeLayoutQuery(layout);
      element.scheduleFunction = schedule.schedule;
      element.cancelFunction = schedule.cancel;
      document.body.append(element);
      await flushMicrotasks();
      await element.updateComplete;
      return element;
    }

    function queryAudioControls(element: AppRoot): HTMLElement {
      return element.shadowRoot!.querySelector("audio-controls") as HTMLElement;
    }

    it("has no refresh button: the panel refreshes itself", async () => {
      const element = await mount(new FakeProfileApi([sampleProfile({ id: 1 })]));

      expect(queryAudioControls(element).shadowRoot!.querySelector("button.refresh")).toBeNull();
    });

    it("does not read the unit, and says why, while it is not connected", async () => {
      const api = new FakeProfileApi([sampleProfile({ id: 1 })]);
      const schedule = new ManualSchedule();

      const element = await mountWithSchedule(api, schedule);

      expect(api.device.audioReads).toBe(0);
      expect(schedule.pending).toBeNull();
      expect(queryAudioControls(element).shadowRoot!.querySelector(".unread")!.textContent).toContain(
        "not connected",
      );
    });

    it("reads when the unit comes up, then again on every tick", async () => {
      const api = new FakeProfileApi([sampleProfile({ id: 1 })]);
      api.device.startConnected();
      const schedule = new ManualSchedule();

      const element = await mountWithSchedule(api, schedule);

      expect(api.device.audioReads).toBe(1);
      expect(queryAudioControls(element).shadowRoot!.querySelector(".readout")).not.toBeNull();
      expect(schedule.delayMs).toBe(AUDIO_POLL_MS);

      await schedule.fire(element);
      expect(api.device.audioReads).toBe(2);
      expect(schedule.pending).not.toBeNull();
    });

    it("skips the read while the phone shows another tab, and reads on opening audio", async () => {
      const api = new FakeProfileApi([sampleProfile({ id: 1 })]);
      api.device.startConnected();
      const schedule = new ManualSchedule();
      const element = await mountWithSchedule(api, schedule, "phone");
      const tabs = element.shadowRoot!.querySelectorAll(".tab");
      await click(tabs[1] as HTMLButtonElement, element);
      const readsOnLoad = api.device.audioReads;

      await schedule.fire(element);
      expect(api.device.audioReads).toBe(readsOnLoad);

      await click(tabs[0] as HTMLButtonElement, element);
      expect(api.device.audioReads).toBe(readsOnLoad + 1);
    });
  });
});
