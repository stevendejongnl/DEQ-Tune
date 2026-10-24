import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client.ts";
import "./access-point-settings.ts";
import { isValidAccessPointKey, type AccessPointSettings } from "./access-point-settings.ts";
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

async function typeInto(element: AccessPointSettings, name: string, value: string): Promise<void> {
  const input = shadow(element).querySelector(`input[name=${name}]`) as HTMLInputElement;
  input.value = value;
  input.dispatchEvent(new InputEvent("input"));
  await element.updateComplete;
}

function saveButton(element: AccessPointSettings): HTMLButtonElement {
  return shadow(element).querySelector(".save") as HTMLButtonElement;
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

  it("saves only when both fields hold the same valid key", async () => {
    const api = piWithAccessPoint();
    const element = await mount(api);

    await typeInto(element, "key", "a much better key");
    expect(saveButton(element).disabled).toBe(true);
    await typeInto(element, "repeated-key", "a much better kez");
    expect(saveButton(element).disabled).toBe(true);
    await typeInto(element, "repeated-key", "a much better key");
    expect(saveButton(element).disabled).toBe(false);

    saveButton(element).click();
    await new Promise((resolve) => setTimeout(resolve));
    await element.updateComplete;

    expect(api.accessPoint?.key).toBe("a much better key");
    expect(shadow(element).querySelector(".warning")).toBeNull();
    expect(shadow(element).querySelector(".message")?.textContent).toContain("next start");
  });

  it("shows the refusal when the Pi refuses the key", async () => {
    const api = piWithAccessPoint();
    const element = await mount(api);
    await typeInto(element, "key", "a much better key");
    await typeInto(element, "repeated-key", "a much better key");
    api.failWith = new ApiError(503, "no helper");

    saveButton(element).click();
    await new Promise((resolve) => setTimeout(resolve));
    await element.updateComplete;

    expect(shadow(element).querySelector(".message")?.textContent).not.toBe("");
    expect(api.accessPoint?.key).toBe("deq-tune-bridge");
  });

  it("refuses an empty key, which would open the network", () => {
    expect(isValidAccessPointKey("")).toBe(false);
    expect(isValidAccessPointKey("short")).toBe(false);
    expect(isValidAccessPointKey("eight ch")).toBe(true);
  });
});
