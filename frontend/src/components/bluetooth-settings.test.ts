import { describe, expect, it } from "vitest";
import "./bluetooth-settings.ts";
import type { BluetoothSettings } from "./bluetooth-settings.ts";
import { closedPi, FakeBluetoothApi, NO_BRIDGE } from "./testing/fake-bluetooth-api.ts";

const NOW = Date.UTC(2026, 9, 26, 12, 0, 0);

async function mount(api: FakeBluetoothApi): Promise<BluetoothSettings> {
  const element = document.createElement("bluetooth-settings") as BluetoothSettings;
  element.api = api;
  element.now = () => NOW;
  element.wait = async () => {};
  document.body.append(element);
  await element.load();
  await element.updateComplete;
  return element;
}

function shadow(element: BluetoothSettings): ShadowRoot {
  return element.shadowRoot!;
}

describe("bluetooth-settings", () => {
  it("says so on a machine with no bridge", async () => {
    const element = await mount(new FakeBluetoothApi(NO_BRIDGE));

    expect(shadow(element).textContent).toContain("no Bluetooth bridge");
    expect(shadow(element).querySelector("button.pair")).toBeNull();
  });

  it("shows a closed window and the bonded phones", async () => {
    const element = await mount(new FakeBluetoothApi(closedPi()));

    expect(shadow(element).querySelector(".window")!.textContent).toContain("Pairing is closed");
    expect(shadow(element).querySelector("ul.phones")!.textContent).toContain("Pixel 8");
  });

  it("names the minutes of the window at each car start", async () => {
    const element = await mount(new FakeBluetoothApi(closedPi()));

    expect(shadow(element).textContent).toContain("For 5 minutes after the DEQ connects");
  });

  it("opens a window with the pair button and shows it as open", async () => {
    const api = new FakeBluetoothApi(closedPi());
    const element = await mount(api);

    await element.openWindow();
    await element.updateComplete;

    expect(api.requests).toBe(1);
    expect(shadow(element).querySelector(".window.open")).not.toBeNull();
    expect(shadow(element).querySelector(".message")).toBeNull();
  });

  it("reports a window that never opened", async () => {
    const api = new FakeBluetoothApi(closedPi());
    api.requestPairingWindow = async () => {
      api.requests += 1;
    };
    const element = await mount(api);

    await element.openWindow();
    await element.updateComplete;

    expect(shadow(element).querySelector(".window.closed")).not.toBeNull();
    expect(shadow(element).querySelector(".message")!.textContent).toContain("did not open pairing");
  });

  it("switches the window at each car start off", async () => {
    const api = new FakeBluetoothApi(closedPi());
    const element = await mount(api);

    const toggle = shadow(element).querySelector<HTMLInputElement>('input[name="pair-at-car-start"]')!;
    toggle.checked = false;
    toggle.dispatchEvent(new Event("change"));
    await element.setPairAtCarStart(false);
    await element.updateComplete;

    expect(api.pairing.pair_at_car_start).toBe(false);
    expect(toggle.checked).toBe(false);
  });

  it("says when it cannot read the Pi", async () => {
    const api = new FakeBluetoothApi(closedPi());
    api.failWith = new Error("offline");
    const element = await mount(api);

    expect(shadow(element).textContent).toContain("Could not read the Bluetooth state");
  });
});
