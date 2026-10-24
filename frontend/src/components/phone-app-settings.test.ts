import { afterEach, describe, expect, it } from "vitest";
import "./phone-app-settings.ts";
import type { PhoneAppSettings } from "./phone-app-settings.ts";
import { FakePhoneAppApi } from "./testing/fake-phone-app-api.ts";

async function mount(api: FakePhoneAppApi): Promise<PhoneAppSettings> {
  const element = document.createElement("phone-app-settings") as PhoneAppSettings;
  element.api = api;
  document.body.append(element);
  await element.updateComplete;
  return element;
}

function shadow(element: PhoneAppSettings): ShadowRoot {
  return element.shadowRoot!;
}

function statusText(element: PhoneAppSettings): string {
  return shadow(element).querySelector("[role=status]")?.textContent ?? "";
}

async function typeInto(element: PhoneAppSettings, name: string, value: string): Promise<void> {
  const input = shadow(element).querySelector(`input[name=${name}]`) as HTMLInputElement;
  input.value = value;
  input.dispatchEvent(new InputEvent("input"));
  await element.updateComplete;
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("phone-app-settings", () => {
  it("says how the phone reaches the Pi now", async () => {
    const element = await mount(new FakePhoneAppApi());

    expect(statusText(element)).toBe("Uses Wi-Fi: the Pi is at 192.168.1.20");
  });

  it("reads again when the car app reports a change", async () => {
    const api = new FakePhoneAppApi({ connection: "searching" });
    const element = await mount(api);
    expect(statusText(element)).toBe("Looking for the Pi…");

    api.report({ connection: "bluetooth", pi_address: null });
    await element.updateComplete;

    expect(statusText(element)).toBe("Uses Bluetooth: the Pi is not on this Wi-Fi network");
  });

  it("does not blame the Wi-Fi network in Bluetooth only", async () => {
    const element = await mount(new FakePhoneAppApi({ mode: "BLUETOOTH", connection: "bluetooth", pi_address: null }));

    expect(statusText(element)).toBe("Uses Bluetooth");
  });

  it("asks the car app to search again", async () => {
    const api = new FakePhoneAppApi();
    const element = await mount(api);

    shadow(element).querySelector<HTMLButtonElement>(".search")!.click();

    expect(api.searches).toBe(1);
  });

  it("saves a new mode at once, and keeps the saved password", async () => {
    const api = new FakePhoneAppApi();
    const element = await mount(api);

    const bluetooth = [...shadow(element).querySelectorAll<HTMLInputElement>("input[name=mode]")].find(
      (input) => input.value === "BLUETOOTH",
    )!;
    bluetooth.click();
    await element.updateComplete;

    expect(api.saved).toEqual([
      { mode: "BLUETOOTH", access_point_url: "http://192.168.4.1:8420", access_point_ssid: "deq-tune", access_point_password: null },
    ]);
  });

  it("shows the access point fields only in access point mode, and saves them", async () => {
    const api = new FakePhoneAppApi();
    const element = await mount(api);
    expect(shadow(element).querySelector("input[name=ssid]")).toBeNull();

    api.report({ mode: "ACCESS_POINT" });
    await element.updateComplete;
    await typeInto(element, "password", "the access point key");
    shadow(element).querySelector<HTMLButtonElement>(".save")!.click();
    await element.updateComplete;

    expect(api.saved.at(-1)?.access_point_password).toBe("the access point key");
    expect(shadow(element).querySelector<HTMLInputElement>("input[name=password]")!.placeholder).toContain("Saved");
  });

  it("offers the permissions only while one is missing", async () => {
    const api = new FakePhoneAppApi({ missing_permissions: true });
    const element = await mount(api);

    shadow(element).querySelector<HTMLButtonElement>(".allow")!.click();
    expect(api.permissionRequests).toBe(1);

    api.report({ missing_permissions: false });
    await element.updateComplete;
    expect(shadow(element).querySelector(".allow")).toBeNull();
  });

  it("stops listening once it leaves the page", async () => {
    const api = new FakePhoneAppApi();
    const element = await mount(api);
    element.remove();

    api.report({ connection: "bluetooth" });

    expect(statusText(element)).toBe("Uses Wi-Fi: the Pi is at 192.168.1.20");
  });
});
