import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client.ts";
import { createFakeLocaleStorage } from "../i18n/testing/fake-locale-storage.ts";
import type { LocaleStorage } from "../i18n/locale.ts";
import { FakeUpdatesApi, updatedPi } from "./testing/fake-updates-api.ts";
import { POSTPONED_VERSION_KEY, SEEN_VERSION_KEY, UPDATES_REFRESH_MS, UpdatesController } from "./updates-controller.ts";

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

function makeController(api: FakeUpdatesApi, storage: LocaleStorage = createFakeLocaleStorage({})) {
  const gaps: number[] = [];
  const controller = new UpdatesController(new FakeHost(), {
    api: () => api,
    storage: () => storage,
    scheduleFunction: () => (_action, delayMs) => {
      gaps.push(delayMs);
      return gaps.length;
    },
    cancelFunction: () => () => {},
  });
  return { controller, gaps, storage };
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
});
