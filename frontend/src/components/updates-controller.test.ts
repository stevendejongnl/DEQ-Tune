import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client.ts";
import { createFakeLocaleStorage } from "../i18n/testing/fake-locale-storage.ts";
import type { LocaleStorage } from "../i18n/locale.ts";
import { FakeUpdatesApi, updatedPi } from "./testing/fake-updates-api.ts";
import {
  POSTPONED_VERSION_KEY,
  RELOADED_FOR_KEY,
  SEEN_VERSION_KEY,
  UPDATES_REFRESH_MS,
  UpdatesController,
} from "./updates-controller.ts";

const PAGE_BUILD = "eed7fb4-2026-10-23T16:00";
const NEWER_BUILD = "8e77c24-2026-10-23T17:26";

/** A host that counts the re-renders the controller asks for. */
class FakeHost {
  updates = 0;
  addController(): void {}
  removeController(): void {}
  requestUpdate(): void {
    this.updates += 1;
  }
  get updateComplete(): Promise<boolean> {
    return Promise.resolve(true);
  }
}

function makeController(
  api: FakeUpdatesApi,
  storage: LocaleStorage = createFakeLocaleStorage({}),
  editing = { unsaved: false },
) {
  const gaps: number[] = [];
  const reloads: number[] = [];
  const controller = new UpdatesController(new FakeHost(), {
    api: () => api,
    storage: () => storage,
    scheduleFunction: () => (_action, delayMs) => {
      gaps.push(delayMs);
      return gaps.length;
    },
    cancelFunction: () => () => {},
    pageBuild: () => PAGE_BUILD,
    hasUnsavedEdits: () => editing.unsaved,
    reload: () => reloads.push(1),
  });
  return { controller, gaps, storage, reloads };
}

describe("UpdatesController", () => {
  it("reads the state on connect, and again after the refresh gap", async () => {
    const api = new FakeUpdatesApi(updatedPi());
    const { controller, gaps } = makeController(api);

    controller.hostConnected();
    await Promise.resolve();
    await Promise.resolve();

    expect(api.reads).toBe(1);
    expect(gaps).toEqual([UPDATES_REFRESH_MS]);
  });

  it("announces a release that the Pi just installed, once", async () => {
    const { controller } = makeController(new FakeUpdatesApi(updatedPi()));
    await controller.load();

    expect(controller.whatsNewVersion).toBe("1.16.0");
    controller.dismissWhatsNew("1.16.0");
    expect(controller.whatsNewVersion).toBeNull();
  });

  it("announces nothing on a machine with no updater", async () => {
    const { controller } = makeController(new FakeUpdatesApi());
    await controller.load();

    expect(controller.whatsNewVersion).toBeNull();
    expect(controller.availableVersion).toBeNull();
  });

  it("offers a waiting release only while automatic updates are off", async () => {
    const api = new FakeUpdatesApi(updatedPi({ latest: "1.17.0", update_available: true }));
    const { controller } = makeController(api);
    await controller.load();
    expect(controller.availableVersion).toBeNull();

    await controller.setAutomatic(false);

    expect(controller.availableVersion).toBe("1.17.0");
  });

  it("stops offering a release the person put off", async () => {
    const api = new FakeUpdatesApi(updatedPi({ latest: "1.17.0", update_available: true, automatic: false }));
    const { controller, storage } = makeController(api);
    await controller.load();

    controller.postpone("1.17.0");

    expect(controller.availableVersion).toBeNull();
    expect(storage.getItem(POSTPONED_VERSION_KEY)).toBe("1.17.0");
  });

  it("remembers the seen version in storage", async () => {
    const storage = createFakeLocaleStorage({ [SEEN_VERSION_KEY]: "1.16.0" });
    const { controller } = makeController(new FakeUpdatesApi(updatedPi()), storage);
    await controller.load();

    expect(controller.whatsNewVersion).toBeNull();
  });

  it("asks the Pi for an update, and says when the machine has no updater", async () => {
    const api = new FakeUpdatesApi(updatedPi());
    const { controller } = makeController(api);

    await controller.requestUpdate();
    expect(api.requests).toBe(1);
    expect(controller.requestState).toBe("requested");

    api.failWith = new ApiError(503, "no updater");
    await controller.requestUpdate();
    expect(controller.requestState).toBe("unsupported");
  });

  it("reloads into the build the bridge serves, once", async () => {
    const { controller, reloads, storage } = makeController(new FakeUpdatesApi(updatedPi({ frontend_build: NEWER_BUILD })));

    await controller.load();
    await controller.load();

    expect(reloads).toHaveLength(1);
    expect(storage.getItem(RELOADED_FOR_KEY)).toBe(NEWER_BUILD);
  });

  it("does not reload while the page is the bridge's own build", async () => {
    const { controller, reloads } = makeController(new FakeUpdatesApi(updatedPi({ frontend_build: PAGE_BUILD })));

    await controller.load();

    expect(reloads).toHaveLength(0);
  });

  it("waits with the reload while edits are unsaved", async () => {
    const editing = { unsaved: true };
    const api = new FakeUpdatesApi(updatedPi({ frontend_build: NEWER_BUILD }));
    const { controller, reloads } = makeController(api, createFakeLocaleStorage({}), editing);

    await controller.load();
    expect(reloads).toHaveLength(0);

    editing.unsaved = false;
    await controller.load();
    expect(reloads).toHaveLength(1);
  });
});
