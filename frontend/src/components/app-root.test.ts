import { afterEach, describe, expect, it } from "vitest";
import "./app-root.ts";
import { AUDIO_POLL_MS, type AppRoot } from "./app-root.ts";
import { FakeProfileApi } from "./testing/fake-profile-api.ts";
import { sampleProfile } from "../dto/testing/sample-profile.ts";
import { flushMicrotasks } from "../testing/flush-microtasks.ts";
import { createFakeLocaleStorage } from "../i18n/testing/fake-locale-storage.ts";
import { createFakeLayoutQuery, type FakeLayoutQuery } from "../testing/fake-layout-query.ts";
import { createFakePageLocationStore, type FakePageLocationStore } from "../testing/fake-page-location-store.ts";
import { FakePhoneAppApi } from "./testing/fake-phone-app-api.ts";
import type { AppLayout } from "../layout-query.ts";
import type { ProfileList } from "./profile-list.ts";
import type { ProfileDto, ProfileUpdateDto } from "../dto/profile.dto.ts";
import { equalizerGains } from "../dto/tuning-data-edits.ts";
import { FakeWifiApi } from "./testing/fake-wifi-api.ts";
import { updatedPi } from "./testing/fake-updates-api.ts";
import { ACCESS_POINT_SETUP_SKIPPED_KEY } from "./access-point-key-controller.ts";
import type { LocaleStorage } from "../i18n/locale.ts";
import type { NotificationDock } from "./notification-dock.ts";

/** A preset with a star, so the sidebar shows it. Most tests here select a
 * preset through its sidebar chip. */
function starredPreset(overrides: Partial<ProfileDto> = {}): ProfileDto {
  return sampleProfile({ favorite: true, ...overrides });
}

/** A small EQ library: one factory EQ and one of the person's own. */
function withLibrary(api: FakeProfileApi): FakeProfileApi {
  api.equalizers = [
    { id: 1, name: "Super Bass", source: "factory", favorite: true, gains: new Array(13).fill(4) },
    { id: 2, name: "Mine", source: "custom", favorite: false, gains: new Array(13).fill(0) },
  ];
  return api;
}

async function mount(
  api: FakeProfileApi,
  layout: AppLayout = "desktop",
  pageLocationStore: FakePageLocationStore = createFakePageLocationStore(),
  accessPointApi: FakeWifiApi = new FakeWifiApi({ saved: [], visible: [] }, null),
  localeStorage: LocaleStorage = createFakeLocaleStorage({}),
): Promise<AppRoot> {
  const element = document.createElement("app-root") as AppRoot;
  element.pageLocationStore = pageLocationStore;
  element.api = api;
  element.accessPointApi = accessPointApi;
  element.localeStorage = localeStorage;
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

function queryPageButton(element: AppRoot, label: string): HTMLButtonElement {
  return [...element.shadowRoot!.querySelectorAll(".page-switch button")].find(
    (button) => button.textContent?.trim() === label,
  ) as HTMLButtonElement;
}

function queryDrawer(element: AppRoot): HTMLElement {
  return element.shadowRoot!.querySelector(".drawer") as HTMLElement;
}

function queryProfilesToggle(element: AppRoot): HTMLButtonElement {
  return element.shadowRoot!.querySelector(".profiles-toggle") as HTMLButtonElement;
}

/** A profile API whose saves wait until the test lets them finish, the way
 * a save to the Pi can take longer than the next pointer move. */
class SlowSaveProfileApi extends FakeProfileApi {
  readonly heldSaves: (() => void)[] = [];
  readonly savedGains: number[][] = [];

  override async updateProfile(id: number, body: ProfileUpdateDto): Promise<ProfileDto> {
    await new Promise<void>((release) => this.heldSaves.push(release));
    if (body.data !== undefined) {
      this.savedGains.push(equalizerGains(body.data));
    }
    return super.updateProfile(id, body);
  }

  async releaseAll(element: AppRoot): Promise<void> {
    while (this.heldSaves.length > 0) {
      this.heldSaves.shift()!();
      await flushMicrotasks();
      await element.updateComplete;
    }
  }
}

// A mounted app-root keeps its header polling on real timers. Removing it
// stops that, so no poll fires while the test environment shuts down.
afterEach(() => {
  document.body.replaceChildren();
});

describe("app-root", () => {
  it("opens with an empty list, and no uncaught error, when the Pi does not answer", async () => {
    const api = new FakeProfileApi([starredPreset({ id: 1 })]);
    api.profilesUnreachable = true;

    const element = await mount(api);

    expect(queryModelRows(element)).toHaveLength(0);
  });

  it("keeps showing the newest gain while older saves are still out", async () => {
    const api = new SlowSaveProfileApi([starredPreset({ id: 1, name: "Mine", source: "custom" })]);
    const element = await mount(api);
    const customName = queryProfileList(element).shadowRoot!.querySelector(
      ".custom-row .name",
    ) as HTMLButtonElement;
    await click(customName, element);
    const eqEditor = element.shadowRoot!.querySelector("eq-editor")!;

    for (const value of [1, 2, 3]) {
      eqEditor.dispatchEvent(new CustomEvent("gain-change", { detail: { band: 4, value } }));
      await flushMicrotasks();
      await element.updateComplete;
    }
    expect(eqEditor.gains[4]).toBe(3);

    await api.releaseAll(element);

    // One save for the first edit, then one for the newest. The middle
    // edit never needed a save of its own.
    expect(api.savedGains.map((gains) => gains[4])).toEqual([1, 3]);
    expect(eqEditor.gains[4]).toBe(3);
    expect((await api.getProfile(1)).data.foundationEq.eqs.LR.banks[0][4]).toBe(3);
  });

  it("starts a new profile clean, not from the selected preset", async () => {
    const preset = starredPreset({ id: 1 });
    preset.data.foundationEq.eqs.LR.banks[0] = new Array(13).fill(4);
    const api = new FakeProfileApi([preset]);
    const element = await mount(api);
    await click(queryFirstChip(element), element);

    const newButton = queryProfileList(element).shadowRoot!.querySelector(
      ".new-profile",
    ) as HTMLButtonElement;
    await click(newButton, element);

    const created = (await api.listProfiles()).find((profile) => profile.source === "custom");
    expect(created?.data.foundationEq.eqs.LR.banks[0]).toEqual(new Array(13).fill(0));
    expect(created?.car_model).toBeNull();
    expect(queryProfileList(element).selectedId).toBe(created?.id);
  });

  it("stars a preset in the library and shows it in the sidebar", async () => {
    const api = new FakeProfileApi([
      sampleProfile({ id: 1, car_model: "mazda_2", speaker_type: "carrozzeria" }),
      sampleProfile({ id: 2, car_model: "mazda_2", speaker_type: "general" }),
    ]);
    const element = await mount(api);
    const list = queryProfileList(element);
    expect(queryModelRows(element)).toHaveLength(0);

    await click(list.shadowRoot!.querySelector(".open-library") as HTMLButtonElement, element);
    await click(list.shadowRoot!.querySelector(".star") as HTMLButtonElement, element);
    await click(list.shadowRoot!.querySelector(".library-back") as HTMLButtonElement, element);

    expect((await api.listProfiles()).every((profile) => profile.favorite)).toBe(true);
    expect(queryModelRows(element)).toHaveLength(1);
  });

  it("activates a profile while the unit is away, and says it waits", async () => {
    const api = new FakeProfileApi([starredPreset({ id: 1, name: "Mine", source: "custom" })]);
    const element = await mount(api);
    await click(
      queryProfileList(element).shadowRoot!.querySelector(".custom-row .name") as HTMLButtonElement,
      element,
    );

    const activation = element.shadowRoot!.querySelector("profile-activation")!;
    await click(activation.shadowRoot!.querySelector(".activate") as HTMLButtonElement, element);

    expect(api.device.activatedProfileIds).toEqual([1]);
    expect(activation.shadowRoot!.textContent).toContain("goes on when the DEQ connects");
    expect(
      queryProfileList(element).shadowRoot!.querySelector(".custom-row .active-tag"),
    ).not.toBeNull();
  });

  it("activates a profile on a connected unit, and says the unit plays it", async () => {
    const api = new FakeProfileApi([starredPreset({ id: 1, name: "Mine", source: "custom" })]);
    api.device.startConnected();
    const element = await mount(api);
    await click(
      queryProfileList(element).shadowRoot!.querySelector(".custom-row .name") as HTMLButtonElement,
      element,
    );

    const activation = element.shadowRoot!.querySelector("profile-activation")!;
    await click(activation.shadowRoot!.querySelector(".activate") as HTMLButtonElement, element);

    expect(activation.shadowRoot!.textContent).toContain("Active on the DEQ");
  });

  it("saves the unit's tune as a custom profile and opens it", async () => {
    const api = new FakeProfileApi([starredPreset({ id: 1 })]);
    api.device.startConnected();
    api.unitTuning = starredPreset().data;
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
      starredPreset({ id: 1, name: "Factory preset", source: "factory" }),
    ]);

    const element = await mount(api);

    expect(queryModelRows(element)).toHaveLength(1);
  });

  it("shows a prompt on the Car page before a profile is chosen", async () => {
    const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]));

    await click(queryPageButton(element, "Car"), element);

    expect(element.shadowRoot!.textContent).toContain("Pick a car profile");
  });

  it("shows the EQ editor for the selected profile", async () => {
    const api = new FakeProfileApi([
      starredPreset({ id: 1, name: "Factory preset", source: "factory" }),
    ]);
    const element = await mount(api);

    await click(queryFirstChip(element), element);

    expect(element.shadowRoot!.querySelector("eq-editor")).not.toBeNull();
  });

  it("persists a gain change through the api for a custom profile", async () => {
    const api = new FakeProfileApi([starredPreset({ id: 1, name: "My EQ", source: "custom" })]);
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
      starredPreset({ id: 1, name: "Factory preset", source: "factory" }),
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
    element.api = new FakeProfileApi([starredPreset({ id: 1 })]);
    element.localeStorage = createFakeLocaleStorage({});
    element.browserLanguages = ["ja-JP"];
    element.layoutQuery = createFakeLayoutQuery("desktop");
    element.pageLocationStore = createFakePageLocationStore();
    document.body.append(element);
    await flushMicrotasks();
    await element.updateComplete;

    const profileListText = queryProfileList(element).shadowRoot!.textContent;
    expect(profileListText).toContain("純正");
  });

  it("switches language via the locale switcher and remembers the choice", async () => {
    const storage = createFakeLocaleStorage({});
    const element = document.createElement("app-root") as AppRoot;
    element.api = new FakeProfileApi([starredPreset({ id: 1 })]);
    element.localeStorage = storage;
    element.browserLanguages = ["en-US"];
    element.layoutQuery = createFakeLayoutQuery("desktop");
    const pageLocationStore = createFakePageLocationStore();
    element.pageLocationStore = pageLocationStore;
    document.body.append(element);
    await flushMicrotasks();
    await element.updateComplete;
    expect(pageLocationStore.hash).not.toContain("lang=");

    element.shadowRoot!.querySelector<HTMLButtonElement>(".open-settings")!.click();
    await element.updateComplete;
    const settings = element.shadowRoot!.querySelector("settings-page")!;
    settings.section = "language";
    await settings.updateComplete;
    const select = settings
      .shadowRoot!.querySelector("locale-switcher")!
      .shadowRoot!.querySelector("select") as HTMLSelectElement;
    select.value = "de";
    select.dispatchEvent(new Event("change"));
    await element.updateComplete;

    const profileListText = queryProfileList(element).shadowRoot!.textContent;
    expect(profileListText).toContain("Meine Profile");
    expect(storage.getItem("deq-tune-locale")).toBe("de");
    // The car app's copy and the Pi's page keep their own saved language.
    // The hash carries the choice from one to the other.
    expect(pageLocationStore.hash).toContain("lang=de");
  });

  it("takes over the language that the page location carries, and saves it", async () => {
    const storage = createFakeLocaleStorage({ "deq-tune-locale": "en" });
    const element = document.createElement("app-root") as AppRoot;
    element.api = new FakeProfileApi([starredPreset({ id: 1 })]);
    element.localeStorage = storage;
    element.browserLanguages = ["en-US"];
    element.layoutQuery = createFakeLayoutQuery("desktop");
    element.pageLocationStore = createFakePageLocationStore("#page=sound&tab=audio&section=updates&lang=de");
    document.body.append(element);
    await flushMicrotasks();
    await element.updateComplete;

    expect(queryProfileList(element).shadowRoot!.textContent).toContain("Meine Profile");
    expect(storage.getItem("deq-tune-locale")).toBe("de");
  });

  describe("Android's app language", () => {
    async function mountInCarApp(phoneApp: FakePhoneAppApi, savedLocale: string) {
      const storage = createFakeLocaleStorage({ "deq-tune-locale": savedLocale });
      const element = document.createElement("app-root") as AppRoot;
      element.api = new FakeProfileApi([starredPreset({ id: 1 })]);
      element.localeStorage = storage;
      element.browserLanguages = ["en-US"];
      element.layoutQuery = createFakeLayoutQuery("desktop");
      element.pageLocationStore = createFakePageLocationStore();
      element.phoneApp = phoneApp;
      document.body.append(element);
      await flushMicrotasks();
      await element.updateComplete;
      return { element, storage };
    }

    it("wins over the page's saved language", async () => {
      const { element, storage } = await mountInCarApp(new FakePhoneAppApi({ language: "de-DE" }), "en");

      expect(queryProfileList(element).shadowRoot!.textContent).toContain("Meine Profile");
      expect(storage.getItem("deq-tune-locale")).toBe("de");
    });

    it("leaves the saved language alone when Android has no choice", async () => {
      const { storage } = await mountInCarApp(new FakePhoneAppApi({ language: null }), "nl");

      expect(storage.getItem("deq-tune-locale")).toBe("nl");
    });

    it("follows a new choice that the car app reports", async () => {
      const phoneApp = new FakePhoneAppApi({ language: null });
      const { element } = await mountInCarApp(phoneApp, "en");

      phoneApp.report({ language: "de" });
      await element.updateComplete;

      expect(queryProfileList(element).shadowRoot!.textContent).toContain("Meine Profile");
    });

    it("gets the language that the person picks in the app", async () => {
      const phoneApp = new FakePhoneAppApi({ language: null });
      const { element } = await mountInCarApp(phoneApp, "en");

      element.shadowRoot!.querySelector<HTMLButtonElement>(".open-settings")!.click();
      await element.updateComplete;
      const settings = element.shadowRoot!.querySelector("settings-page")!;
      settings.section = "language";
      await settings.updateComplete;
      const select = settings
        .shadowRoot!.querySelector("locale-switcher")!
        .shadowRoot!.querySelector("select") as HTMLSelectElement;
      select.value = "nl";
      select.dispatchEvent(new Event("change"));
      await element.updateComplete;

      expect(phoneApp.languagesSet).toEqual(["nl"]);
    });
  });

  it("starts with the profiles drawer closed", async () => {
    const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]));

    expect(queryDrawer(element).classList.contains("open")).toBe(false);
    expect(element.shadowRoot!.querySelector(".drawer-backdrop")).toBeNull();
  });

  it("opens the profiles drawer from the header toggle", async () => {
    const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]));

    await click(queryProfilesToggle(element), element);

    expect(queryDrawer(element).classList.contains("open")).toBe(true);
    expect(element.shadowRoot!.querySelector(".drawer-backdrop")).not.toBeNull();
  });

  it("closes the profiles drawer when the backdrop is clicked", async () => {
    const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]));
    await click(queryProfilesToggle(element), element);

    const backdrop = element.shadowRoot!.querySelector(".drawer-backdrop") as HTMLElement;
    backdrop.dispatchEvent(new Event("click"));
    await flushMicrotasks();
    await element.updateComplete;

    expect(queryDrawer(element).classList.contains("open")).toBe(false);
  });

  it("closes the profiles drawer when Escape is pressed", async () => {
    const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]));
    await click(queryProfilesToggle(element), element);

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await element.updateComplete;

    expect(queryDrawer(element).classList.contains("open")).toBe(false);
  });

  it("shows the brand, the speaker type and the model name above the panels", async () => {
    const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]));

    await click(queryFirstChip(element), element);

    const heading = element.shadowRoot!.querySelector(".heading-row")!;
    expect(heading.textContent).toContain("Mazda");
    expect(heading.textContent).toContain("For Normal Speaker");
    expect(heading.querySelector(".profile-title")!.textContent).toContain("Mazda3");
  });

  it("shows the sound on the Sound page, and opens a picked profile on the Car page", async () => {
    const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]));

    expect(element.shadowRoot!.querySelector(".tab-bar")).toBeNull();
    expect(element.shadowRoot!.querySelector("audio-controls")).not.toBeNull();
    expect(element.shadowRoot!.querySelector("equalizer-editor")).not.toBeNull();
    expect(element.shadowRoot!.querySelector("dsp-panel")).not.toBeNull();
    expect(element.shadowRoot!.querySelector("speaker-panel")).toBeNull();

    await click(queryFirstChip(element), element);

    expect(queryPageButton(element, "Car").getAttribute("aria-pressed")).toBe("true");
    expect(element.shadowRoot!.querySelector("speaker-panel")).not.toBeNull();
    expect(element.shadowRoot!.querySelector("eq-editor.car-correction")).not.toBeNull();
    expect(element.shadowRoot!.querySelector("equalizer-editor")).toBeNull();
  });

  it("opens the active car profile on the Car page when none is picked", async () => {
    const api = new FakeProfileApi([starredPreset({ id: 1, name: "Dusty", source: "custom" })]);
    await api.activateProfile(1);
    const element = await mount(api);

    await click(queryPageButton(element, "Car"), element);

    expect(queryProfileList(element).selectedId).toBe(1);
    expect(element.shadowRoot!.querySelector("speaker-panel")).not.toBeNull();
  });

  it("names the active car profile on the Sound page, and opens it there", async () => {
    const api = new FakeProfileApi([starredPreset({ id: 1, name: "Dusty", source: "custom" })]);
    await api.activateProfile(1);
    const element = await mount(api);

    const carLine = element.shadowRoot!.querySelector(".car-line") as HTMLButtonElement;
    expect(carLine.textContent).toContain("Dusty");
    await click(carLine, element);

    expect(queryProfileList(element).selectedId).toBe(1);
    expect(element.shadowRoot!.querySelector("speaker-panel")).not.toBeNull();
  });

  it("passes the EQ library and the live simulation ids to the panel", async () => {
    const api = withLibrary(new FakeProfileApi([starredPreset({ id: 1 })]));
    const element = await mount(api);

    const panel = element.shadowRoot!.querySelector("dsp-panel")!;
    // No EQ, then the two EQs of the library.
    expect(panel.shadowRoot!.querySelectorAll(".tile")).toHaveLength(3);
    expect(panel.shadowRoot!.querySelectorAll(".option")).toHaveLength(3);
  });

  it("picks an EQ, and the panel marks it as the one that plays", async () => {
    const api = withLibrary(new FakeProfileApi([starredPreset({ id: 1 })]));
    const element = await mount(api);
    const panel = element.shadowRoot!.querySelector("dsp-panel")!;

    panel.dispatchEvent(new CustomEvent("activate-equalizer", { detail: { id: 2 } }));
    await flushMicrotasks();
    await element.updateComplete;

    expect(api.device.activatedEqualizerIds).toEqual([2]);
    expect(panel.activeEqualizerId).toBe(2);
  });

  it("makes one copy of a factory EQ on quick drags, and the copy plays", async () => {
    const api = withLibrary(new FakeProfileApi([starredPreset({ id: 1 })]));
    await api.activateEqualizer(1);
    const element = await mount(api);
    const editor = element.shadowRoot!.querySelector("equalizer-editor")!;
    expect(editor.equalizer?.name).toBe("Super Bass");

    const first = [...new Array(13).fill(4)];
    first[0] = 6;
    const second = [...first];
    second[5] = -2;
    editor.dispatchEvent(new CustomEvent("equalizer-gains", { detail: { gains: first } }));
    editor.dispatchEvent(new CustomEvent("equalizer-gains", { detail: { gains: second } }));
    await flushMicrotasks();
    await flushMicrotasks();
    await element.updateComplete;

    expect(api.createdEqualizers).toBe(1);
    const copy = (await api.listEqualizers()).find((equalizer) => equalizer.name === "Super Bass (copy)")!;
    expect(copy.gains).toEqual(second);
    expect(api.device.activatedEqualizerIds.at(-1)).toBe(copy.id);
    expect(editor.equalizer?.id).toBe(copy.id);
  });

  it("starts a new EQ of the person's own on a drag while No EQ plays", async () => {
    const api = withLibrary(new FakeProfileApi([starredPreset({ id: 1 })]));
    await api.activateEqualizer(null);
    const element = await mount(api);
    const editor = element.shadowRoot!.querySelector("equalizer-editor")!;
    const gains = new Array(13).fill(0);
    gains[1] = 3;

    editor.dispatchEvent(new CustomEvent("equalizer-gains", { detail: { gains } }));
    await flushMicrotasks();
    await flushMicrotasks();
    await element.updateComplete;

    const created = (await api.listEqualizers()).find((equalizer) => equalizer.name === "My EQ")!;
    expect(created.gains).toEqual(gains);
    expect(api.device.activatedEqualizerIds.at(-1)).toBe(created.id);
  });

  it("saves a curve edit of an EQ of the person's own, and deletes it", async () => {
    const api = withLibrary(new FakeProfileApi([starredPreset({ id: 1 })]));
    await api.activateEqualizer(2);
    const element = await mount(api);
    const editor = element.shadowRoot!.querySelector("equalizer-editor")!;

    editor.dispatchEvent(
      new CustomEvent("equalizer-gains", { detail: { gains: new Array(13).fill(3) } }),
    );
    await flushMicrotasks();
    await element.updateComplete;
    expect(api.createdEqualizers).toBe(0);
    expect((await api.listEqualizers()).find((equalizer) => equalizer.id === 2)?.gains).toEqual(
      new Array(13).fill(3),
    );

    editor.dispatchEvent(new CustomEvent("delete-equalizer", { detail: { id: 2 } }));
    await flushMicrotasks();
    await element.updateComplete;
    expect(await api.listEqualizers()).toHaveLength(1);
  });

  it("sends a live simulation choice to the unit", async () => {
    const api = new FakeProfileApi([starredPreset({ id: 1 })]);
    const element = await mount(api);

    element.shadowRoot!.querySelector("dsp-panel")!.dispatchEvent(
      new CustomEvent("live-simulation-change", { detail: { id: "CONCERT_HALL" } }),
    );
    await element.updateComplete;

    expect(api.device.selectedLiveSimulations).toEqual(["CONCERT_HALL"]);
  });

  it("renders only the active tab in the phone layout", async () => {
    const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]), "phone");
    await click(queryFirstChip(element), element);
    const eqTab = element.shadowRoot!.querySelectorAll(".tab")[1] as HTMLButtonElement;
    await click(eqTab, element);

    expect(element.shadowRoot!.querySelector(".tab-bar")).not.toBeNull();
    expect(element.shadowRoot!.querySelector("equalizer-editor")).not.toBeNull();
    expect(element.shadowRoot!.querySelector("dsp-panel")).not.toBeNull();
    expect(element.shadowRoot!.querySelector("speaker-panel")).toBeNull();
  });

  it("keeps the open phone tab in the page location", async () => {
    const pageLocationStore = createFakePageLocationStore();
    const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]), "phone", pageLocationStore);
    const eqTab = element.shadowRoot!.querySelectorAll(".tab")[1] as HTMLButtonElement;
    await click(eqTab, element);

    expect(pageLocationStore.hash).toBe("#page=sound&tab=eq&section=updates");
  });

  it("opens the tab that the page location names after a reload", async () => {
    const pageLocationStore = createFakePageLocationStore("#page=sound&tab=eq&section=updates");
    const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]), "phone", pageLocationStore);

    const eqTab = element.shadowRoot!.querySelectorAll(".tab")[1] as HTMLButtonElement;
    expect(eqTab.getAttribute("aria-pressed")).toBe("true");
    expect(element.shadowRoot!.querySelector("equalizer-editor")).not.toBeNull();
  });

  it("opens the settings section that the page location names after a reload", async () => {
    const pageLocationStore = createFakePageLocationStore("#page=settings&tab=audio&section=wifi");
    const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]), "phone", pageLocationStore);

    const settingsPage = element.shadowRoot!.querySelector("settings-page") as HTMLElement & { section: string };
    expect(settingsPage.section).toBe("wifi");
  });

  it("does not open the phone app section outside the car app", async () => {
    const pageLocationStore = createFakePageLocationStore("#page=settings&tab=audio&section=phone");
    const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]), "phone", pageLocationStore);

    const settingsPage = element.shadowRoot!.querySelector("settings-page") as HTMLElement & { section: string };
    expect(settingsPage.section).toBe("updates");
  });

  it("swaps the panel when another phone tab is pressed", async () => {
    const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]), "phone");
    await click(queryFirstChip(element), element);
    const eqTab = element.shadowRoot!.querySelectorAll(".tab")[1] as HTMLButtonElement;
    await click(eqTab, element);

    const carTab = element.shadowRoot!.querySelectorAll(".tab")[2] as HTMLButtonElement;
    await click(carTab, element);

    expect(carTab.getAttribute("aria-pressed")).toBe("true");
    expect(element.shadowRoot!.querySelector("speaker-panel")).not.toBeNull();
    expect(element.shadowRoot!.querySelector("equalizer-editor")).toBeNull();
    // The car's own correction curve sits on the Car tab.
    expect(element.shadowRoot!.querySelector("eq-editor.car-correction")).not.toBeNull();
  });

  it("edits a factory preset without saving it", async () => {
    const api = new FakeProfileApi([
      starredPreset({ id: 1, name: "Factory preset", source: "factory" }),
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
    const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]));
    await click(queryFirstChip(element), element);

    expect(element.shadowRoot!.querySelector(".badge")!.textContent).toContain("Factory preset");
    expect(element.shadowRoot!.querySelector(".start-hint")).not.toBeNull();
  });

  it("counts every changed band in the badge", async () => {
    const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]));
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
    const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]));
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
      starredPreset({ id: 1, name: "Factory preset", source: "factory" }),
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
    const element = await mount(new FakeProfileApi([starredPreset({ id: 1 }), starredPreset({ id: 2, car_model: "mazda_6" })]));
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

  describe("undo on the car correction curve", () => {
    function correctionUndo(element: AppRoot): HTMLButtonElement {
      return element.shadowRoot!.querySelector(".area-correction .undo") as HTMLButtonElement;
    }

    async function dragBand(element: AppRoot, band: number, values: number[]): Promise<void> {
      const editor = element.shadowRoot!.querySelector("eq-editor.car-correction")!;
      editor.dispatchEvent(new CustomEvent("gain-edit-start"));
      for (const value of values) {
        editor.dispatchEvent(new CustomEvent("gain-change", { detail: { band, value } }));
        await flushMicrotasks();
        await element.updateComplete;
      }
    }

    function shownGains(element: AppRoot): number[] {
      const editor = element.shadowRoot!.querySelector("eq-editor.car-correction") as HTMLElement & {
        gains: number[];
      };
      return editor.gains;
    }

    it("has nothing to undo before an edit", async () => {
      const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]));
      await click(queryFirstChip(element), element);

      expect(correctionUndo(element).disabled).toBe(true);
    });

    it("takes a whole drag back in one step", async () => {
      const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]));
      await click(queryFirstChip(element), element);
      const before = [...shownGains(element)];
      await dragBand(element, 2, [1.5, 3, 4.5]);

      await click(correctionUndo(element), element);

      expect(shownGains(element)).toEqual(before);
      expect(correctionUndo(element).disabled).toBe(true);
      expect(element.shadowRoot!.querySelector(".badge")!.textContent).toContain("Factory preset");
    });

    it("goes back one step at a time", async () => {
      const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]));
      await click(queryFirstChip(element), element);
      await dragBand(element, 1, [2]);
      await dragBand(element, 2, [3]);

      await click(correctionUndo(element), element);

      expect(shownGains(element)[1]).toBe(2);
      expect(shownGains(element)[2]).toBe(0);
      expect(correctionUndo(element).disabled).toBe(false);
    });

    it("saves the undone curve of a custom profile", async () => {
      const api = new FakeProfileApi([starredPreset({ id: 1, source: "custom" })]);
      await api.activateProfile(1);
      const element = await mount(api);
      await click(queryPageButton(element, "Car"), element);
      await dragBand(element, 4, [6]);

      await click(correctionUndo(element), element);
      await flushMicrotasks();

      const stored = await api.getProfile(1);
      expect(equalizerGains(stored.data)[4]).toBe(0);
    });

    it("forgets the steps when another profile comes in", async () => {
      const element = await mount(
        new FakeProfileApi([starredPreset({ id: 1 }), starredPreset({ id: 2, car_model: "mazda_6" })]),
      );
      element.confirmDiscard = () => true;
      await click(queryFirstChip(element), element);
      await dragBand(element, 2, [4.5]);

      const otherChip = queryProfileList(element).shadowRoot!.querySelectorAll(".chip")[1];
      await click(otherChip as HTMLButtonElement, element);

      expect(correctionUndo(element).disabled).toBe(true);
    });
  });

  describe("following the Pi's build", () => {
    async function mountOnOlderBuild(api: FakeProfileApi, reloads: string[]): Promise<AppRoot> {
      api.updates.updates = updatedPi({ frontend_build: "newer-build" });
      const element = document.createElement("app-root") as AppRoot;
      element.pageLocationStore = createFakePageLocationStore();
      element.api = api;
      element.accessPointApi = new FakeWifiApi({ saved: [], visible: [] }, null);
      element.localeStorage = createFakeLocaleStorage({});
      element.browserLanguages = ["en-US"];
      element.layoutQuery = createFakeLayoutQuery("desktop");
      element.pageBuild = "older-build";
      element.reloadFunction = () => reloads.push("reload");
      document.body.append(element);
      await flushMicrotasks();
      await element.updateComplete;
      return element;
    }

    it("reloads into the Pi's newer build", async () => {
      const reloads: string[] = [];
      await mountOnOlderBuild(new FakeProfileApi([starredPreset({ id: 1 })]), reloads);

      expect(reloads).toEqual(["reload"]);
    });

    it("does not reload while the person types in a field", async () => {
      const field = document.createElement("input");
      document.body.append(field);
      field.focus();
      const reloads: string[] = [];

      await mountOnOlderBuild(new FakeProfileApi([starredPreset({ id: 1 })]), reloads);

      expect(reloads).toEqual([]);
    });
  });

  describe("the access point key", () => {
    function piOnTheDefaultKey(): FakeWifiApi {
      return new FakeWifiApi({ saved: [], visible: [] }, { ssid: "deq-tune", key: "deq-tune-bridge" });
    }

    async function mountWithAccessPoint(
      accessPointApi: FakeWifiApi,
      localeStorage: LocaleStorage = createFakeLocaleStorage({}),
    ): Promise<AppRoot> {
      const element = await mount(
        new FakeProfileApi([starredPreset({ id: 1 })]),
        "desktop",
        createFakePageLocationStore(),
        accessPointApi,
        localeStorage,
      );
      await flushMicrotasks();
      await element.updateComplete;
      return element;
    }

    function dock(element: AppRoot): NotificationDock {
      return element.shadowRoot!.querySelector("notification-dock")!;
    }

    it("asks for an own key at the first start on the default key", async () => {
      const element = await mountWithAccessPoint(piOnTheDefaultKey());

      expect(element.shadowRoot!.querySelector("access-point-setup")).not.toBeNull();
    });

    it("asks nothing once the key is the person's own", async () => {
      const api = new FakeWifiApi({ saved: [], visible: [] }, { ssid: "deq-tune", key: "my own key" });
      const element = await mountWithAccessPoint(api);

      expect(element.shadowRoot!.querySelector("access-point-setup")).toBeNull();
      expect(dock(element).shadowRoot!.querySelector(".access-point")).toBeNull();
    });

    it("moves to a dock notice after Later, which opens the Wi-Fi settings", async () => {
      const element = await mountWithAccessPoint(piOnTheDefaultKey());

      element.shadowRoot!.querySelector("access-point-setup")!.dispatchEvent(
        new CustomEvent("access-point-setup-skipped"),
      );
      await element.updateComplete;
      await dock(element).updateComplete;
      const notice = dock(element).shadowRoot!.querySelector(".access-point .primary") as HTMLButtonElement;
      notice.click();
      await element.updateComplete;

      expect(element.shadowRoot!.querySelector("access-point-setup")).toBeNull();
      expect(element.shadowRoot!.querySelector("main settings-page")).not.toBeNull();
    });

    it("hides the notice while the Wi-Fi settings, with the key form, are open", async () => {
      const storage = createFakeLocaleStorage({ [ACCESS_POINT_SETUP_SKIPPED_KEY]: "true" });
      const element = await mountWithAccessPoint(piOnTheDefaultKey(), storage);
      await dock(element).updateComplete;

      (dock(element).shadowRoot!.querySelector(".access-point .primary") as HTMLButtonElement).click();
      await element.updateComplete;
      await dock(element).updateComplete;

      expect(dock(element).shadowRoot!.querySelector(".access-point")).toBeNull();
    });

    it("shows the notice, not the setup, after an earlier Later", async () => {
      const storage = createFakeLocaleStorage({ [ACCESS_POINT_SETUP_SKIPPED_KEY]: "true" });
      const element = await mountWithAccessPoint(piOnTheDefaultKey(), storage);
      await dock(element).updateComplete;

      expect(element.shadowRoot!.querySelector("access-point-setup")).toBeNull();
      expect(dock(element).shadowRoot!.querySelector(".access-point")).not.toBeNull();
    });

    it("drops the setup and the notice once the key is saved", async () => {
      const element = await mountWithAccessPoint(piOnTheDefaultKey());
      const setup = element.shadowRoot!.querySelector("access-point-setup")!;

      setup.dispatchEvent(
        new CustomEvent("access-point-key-saved", {
          detail: { accessPoint: { ssid: "deq-tune", uses_default_key: false } },
        }),
      );
      setup.dispatchEvent(new CustomEvent("access-point-setup-closed"));
      await element.updateComplete;
      await dock(element).updateComplete;

      expect(element.shadowRoot!.querySelector("access-point-setup")).toBeNull();
      expect(dock(element).shadowRoot!.querySelector(".access-point")).toBeNull();
    });
  });

  it("puts the save actions in a bar on the phone", async () => {
    const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]), "phone");
    await click(queryFirstChip(element), element);
    const speakersTab = element.shadowRoot!.querySelectorAll(".tab")[2] as HTMLButtonElement;
    await click(speakersTab, element);
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

  it("opens the settings page from the header's gear button", async () => {
    const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]));

    element.shadowRoot!.querySelector<HTMLButtonElement>(".open-settings")!.click();
    await element.updateComplete;

    expect(element.shadowRoot!.querySelector("main settings-page")).not.toBeNull();
    expect(element.shadowRoot!.querySelector("header locale-switcher")).toBeNull();
  });

  it("opens the system section when the status pill asks for it", async () => {
    const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]));

    element.shadowRoot!.querySelector("device-status")!.dispatchEvent(
      new CustomEvent("open-system", { bubbles: true, composed: true }),
    );
    await element.updateComplete;

    expect(element.shadowRoot!.querySelector("settings-page")!.section).toBe("system");
  });

  it("opens settings from the phone's tab bar, and leaves it for another tab", async () => {
    const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]), "phone");
    const tabs = [...element.shadowRoot!.querySelectorAll<HTMLButtonElement>(".tab-bar .tab")];
    expect(tabs.map((tab) => tab.textContent!.trim())).toEqual(["Audio", "EQ", "Car", "Settings"]);
    tabs[3].click();
    await element.updateComplete;
    expect(element.shadowRoot!.querySelector("settings-page")).not.toBeNull();

    element.shadowRoot!.querySelector<HTMLButtonElement>(".tab-bar .tab")!.click();
    await element.updateComplete;

    expect(element.shadowRoot!.querySelector("settings-page")).toBeNull();
  });

  it("moves to the phone layout when the viewport becomes narrow", async () => {
    const layoutQuery: FakeLayoutQuery = createFakeLayoutQuery("desktop");
    const element = document.createElement("app-root") as AppRoot;
    element.api = new FakeProfileApi([starredPreset({ id: 1 })]);
    element.localeStorage = createFakeLocaleStorage({});
    element.browserLanguages = ["en-US"];
    element.layoutQuery = layoutQuery;
    element.pageLocationStore = createFakePageLocationStore();
    document.body.append(element);
    await flushMicrotasks();
    await element.updateComplete;
    expect(element.shadowRoot!.querySelector(".tab-bar")).toBeNull();

    layoutQuery.setLayout("phone");
    await element.updateComplete;

    expect(element.shadowRoot!.querySelector(".tab-bar")).not.toBeNull();
  });

  it("closes the profiles drawer after selecting a profile", async () => {
    const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]));
    await click(queryProfilesToggle(element), element);

    await click(queryFirstChip(element), element);

    expect(queryDrawer(element).classList.contains("open")).toBe(false);
  });
  describe("audio panel and the unit link", () => {
    /** Holds the one waiting timer, so a test fires it instead of sleeping. */
    /** Holds the audio poll. The same seam also carries the updates
     * refresh, which `updates-controller.test.ts` covers, so this schedule
     * lets that one go by. */
    class ManualSchedule {
      pending: (() => void) | null = null;
      delayMs: number | null = null;
      schedule = (action: () => void, delayMs: number): unknown => {
        if (delayMs !== AUDIO_POLL_MS) {
          return 0;
        }
        this.pending = action;
        this.delayMs = delayMs;
        return 1;
      };
      cancel = (handle: unknown): void => {
        if (handle === 1) {
          this.pending = null;
        }
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
      carScreen = false,
      pageLocationStore: FakePageLocationStore = createFakePageLocationStore(),
    ): Promise<AppRoot> {
      const element = document.createElement("app-root") as AppRoot;
      element.carScreen = carScreen;
      element.api = api;
      element.localeStorage = createFakeLocaleStorage({});
      element.browserLanguages = ["en-US"];
      element.layoutQuery = createFakeLayoutQuery(layout);
      element.pageLocationStore = pageLocationStore;
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
      const element = await mount(new FakeProfileApi([starredPreset({ id: 1 })]));

      expect(queryAudioControls(element).shadowRoot!.querySelector("button.refresh")).toBeNull();
    });

    it("does not read the unit, and says why, while it is not connected", async () => {
      const api = new FakeProfileApi([starredPreset({ id: 1 })]);
      const schedule = new ManualSchedule();

      const element = await mountWithSchedule(api, schedule);

      expect(api.device.audioReads).toBe(0);
      expect(schedule.pending).toBeNull();
      expect(queryAudioControls(element).shadowRoot!.querySelector(".unread")!.textContent).toContain(
        "not connected",
      );
    });

    it("says that the Pi does not answer, and not that the unit is down", async () => {
      const api = new FakeProfileApi([starredPreset({ id: 1 })]);
      api.device.unreachable = true;

      const element = await mountWithSchedule(api, new ManualSchedule());

      const unread = queryAudioControls(element).shadowRoot!.querySelector(".unread")!.textContent!;
      expect(unread).toContain("The Pi does not answer");
      expect(unread).not.toContain("not connected");
    });

    it("reads when the unit comes up, then again on every tick", async () => {
      const api = new FakeProfileApi([starredPreset({ id: 1 })]);
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

    it("sends only the newest volume that waits while one is on its way", async () => {
      const api = new FakeProfileApi([starredPreset({ id: 1 })]);
      api.device.startConnected();
      const element = await mountWithSchedule(api, new ManualSchedule());
      const controls = queryAudioControls(element);
      const sendVolume = (volumeDb: number) =>
        controls.dispatchEvent(new CustomEvent("volume-change", { detail: { volumeDb }, bubbles: true, composed: true }));

      sendVolume(-10);
      sendVolume(-7);
      sendVolume(-3);
      await flushMicrotasks();
      await flushMicrotasks();

      expect(api.device.volumeWrites).toEqual([-10, -3]);
    });

    it("skips the read while the phone shows another tab, and reads on opening audio", async () => {
      const api = new FakeProfileApi([starredPreset({ id: 1 })]);
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
    describe("on Android Auto's screen", () => {
      function queryCarScreen(element: AppRoot): HTMLElement {
        return element.shadowRoot!.querySelector("car-screen") as HTMLElement;
      }

      async function mountCarScreen(api: FakeProfileApi, schedule: ManualSchedule, hash = ""): Promise<AppRoot> {
        return mountWithSchedule(api, schedule, "phone", true, createFakePageLocationStore(hash));
      }

      it("opens on the car screen, with the link status and no tab bar", async () => {
        const element = await mountCarScreen(new FakeProfileApi([starredPreset({ id: 1 })]), new ManualSchedule());

        expect(queryCarScreen(element)).not.toBeNull();
        expect(element.shadowRoot!.querySelector(".tab-bar")).toBeNull();
        expect(queryCarScreen(element).querySelector('device-status[slot="status"]')).not.toBeNull();
      });

      it("shows no notice: no release notes, no update offer, no access point step", async () => {
        const api = new FakeProfileApi([starredPreset({ id: 1 })]);
        const element = await mountCarScreen(api, new ManualSchedule());

        expect(element.shadowRoot!.querySelector("notification-dock")).toBeNull();
        expect(element.shadowRoot!.querySelector("access-point-setup")).toBeNull();
        expect(element.shadowRoot!.querySelector(".content")).toBeNull();
      });

      it("reads the unit only while the Audio tab is open", async () => {
        const api = new FakeProfileApi([starredPreset({ id: 1 })]);
        api.device.startConnected();
        const schedule = new ManualSchedule();
        const element = await mountCarScreen(api, schedule);

        await schedule.fire(element);
        expect(api.device.audioReads).toBe(0);

        queryCarScreen(element).dispatchEvent(new CustomEvent("tab-change", { detail: { tab: "audio" } }));
        await flushMicrotasks();
        expect(api.device.audioReads).toBe(1);

        await schedule.fire(element);
        expect(api.device.audioReads).toBe(2);
      });

      it("plays the tapped car profile and mutes the unit", async () => {
        const api = new FakeProfileApi([starredPreset({ id: 1 })]);
        api.device.startConnected();
        const element = await mountCarScreen(api, new ManualSchedule());
        const screen = queryCarScreen(element);

        screen.dispatchEvent(new CustomEvent("activate-profile", { detail: { id: 1 } }));
        screen.dispatchEvent(new CustomEvent("mute-change", { detail: { muted: true } }));
        await flushMicrotasks();
        await element.updateComplete;

        expect(api.device.activatedProfileIds).toEqual([1]);
        expect(api.device.muteWrites).toEqual([true]);
      });
    });
  });
});
