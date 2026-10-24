import { describe, expect, it } from "vitest";
import "./access-point-settings.ts";
import type { AccessPointSettings } from "./access-point-settings.ts";
import { FakeWifiApi } from "./testing/fake-wifi-api.ts";

function piWithAccessPoint(key = "deq-tune-bridge"): FakeWifiApi {
  return new FakeWifiApi({ saved: [], visible: [] }, { ssid: "deq-tune", key });
}

async function mount(api: FakeWifiApi): Promise<AccessPointSettings> {
  const element = document.createElement("access-point-settings") as AccessPointSettings;
  element.api = api;
  document.body.append(element);
  await element.load();
  await element.updateComplete;
  return element;
}

function shadow(element: AccessPointSettings): ShadowRoot {
  return element.shadowRoot!;
}

describe("access-point-settings", () => {
  it("warns while the access point uses the public default key", async () => {
    const element = await mount(piWithAccessPoint());

    expect(shadow(element).querySelector(".warning")).not.toBeNull();
    expect(shadow(element).textContent).toContain("deq-tune");
  });

  it("does not warn once the key is the person's own", async () => {
    const element = await mount(piWithAccessPoint("my own key"));

    expect(shadow(element).querySelector(".warning")).toBeNull();
  });

  it("renders nothing for a Pi without an access point", async () => {
    const api = new FakeWifiApi({ saved: [], visible: [] }, null);
    const element = await mount(api);

    expect(shadow(element).querySelector("section")).toBeNull();
  });

  it("drops the warning once its form saved a key", async () => {
    const element = await mount(piWithAccessPoint());

    shadow(element)
      .querySelector("access-point-key-form")!
      .dispatchEvent(
        new CustomEvent("access-point-key-saved", {
          detail: { accessPoint: { ssid: "deq-tune", uses_default_key: false } },
        }),
      );
    await element.updateComplete;

    expect(shadow(element).querySelector(".warning")).toBeNull();
  });
});
