import { describe, expect, it } from "vitest";
import { createFakeLocaleStorage } from "../i18n/testing/fake-locale-storage.ts";
import type { LocaleStorage } from "../i18n/locale.ts";
import { ACCESS_POINT_SETUP_SKIPPED_KEY, AccessPointKeyController } from "./access-point-key-controller.ts";
import { FakeWifiApi } from "./testing/fake-wifi-api.ts";

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

function piWithKey(key: string | null): FakeWifiApi {
  return new FakeWifiApi({ saved: [], visible: [] }, key === null ? null : { ssid: "deq-tune", key });
}

function makeController(api: FakeWifiApi, storage: LocaleStorage = createFakeLocaleStorage({})) {
  return new AccessPointKeyController(new FakeHost(), { api: () => api, storage: () => storage });
}

describe("AccessPointKeyController", () => {
  it("opens the setup while the Pi uses the default key", async () => {
    const controller = makeController(piWithKey("deq-tune-bridge"));

    await controller.load();

    expect(controller.setupOpen).toBe(true);
    expect(controller.showsNotice).toBe(false);
  });

  it("asks for nothing once the key is the person's own", async () => {
    const controller = makeController(piWithKey("my own key"));

    await controller.load();

    expect(controller.setupOpen).toBe(false);
    expect(controller.showsNotice).toBe(false);
  });

  it("asks for nothing on a Pi without an access point", async () => {
    const controller = makeController(piWithKey(null));

    await controller.load();

    expect(controller.setupOpen).toBe(false);
    expect(controller.showsNotice).toBe(false);
  });

  it("puts a notice in the dock after Later, and remembers it", async () => {
    const storage = createFakeLocaleStorage({});
    const controller = makeController(piWithKey("deq-tune-bridge"), storage);
    await controller.load();

    controller.skip();

    expect(controller.setupOpen).toBe(false);
    expect(controller.showsNotice).toBe(true);
    expect(storage.getItem(ACCESS_POINT_SETUP_SKIPPED_KEY)).not.toBeNull();
  });

  it("does not open the setup again after Later, but keeps the notice", async () => {
    const storage = createFakeLocaleStorage({ [ACCESS_POINT_SETUP_SKIPPED_KEY]: "true" });
    const controller = makeController(piWithKey("deq-tune-bridge"), storage);

    await controller.load();

    expect(controller.setupOpen).toBe(false);
    expect(controller.showsNotice).toBe(true);
  });

  it("drops the notice once a key is saved", async () => {
    const storage = createFakeLocaleStorage({ [ACCESS_POINT_SETUP_SKIPPED_KEY]: "true" });
    const controller = makeController(piWithKey("deq-tune-bridge"), storage);
    await controller.load();

    controller.accept({ ssid: "deq-tune", uses_default_key: false });

    expect(controller.showsNotice).toBe(false);
  });
});
