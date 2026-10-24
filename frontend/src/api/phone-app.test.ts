import { describe, expect, it } from "vitest";
import { PHONE_APP_CHANGE_EVENT, PHONE_APP_FILE_SAVED_EVENT, phoneAppApi } from "./phone-app.ts";

/** A window with the car app's interface, as the car app's web view has. */
function windowWithAndroid(stateJson: string): { host: Window; saved: string[] } {
  const host = new EventTarget() as unknown as Window & { DeqAndroidSettings: object };
  const saved: string[] = [];
  host.DeqAndroidSettings = {
    read: () => stateJson,
    save: (changeJson: string) => saved.push(changeJson),
    searchAgain: () => undefined,
    askPermissions: () => undefined,
    setLanguage: () => undefined,
    saveFile: (fileName: string) =>
      host.dispatchEvent(new CustomEvent(PHONE_APP_FILE_SAVED_EVENT, { detail: { saved: fileName !== "cancel.json" } })),
  };
  return { host, saved };
}

const STATE = {
  mode: "AUTOMATIC",
  connection: "bluetooth",
  pi_address: null,
  access_point_url: "http://192.168.4.1:8420",
  access_point_ssid: "deq-tune",
  has_access_point_password: true,
  missing_permissions: false,
  app_version: "0.1.0",
  language: null,
};

describe("phoneAppApi", () => {
  it("is null in a browser, which has no car app interface", () => {
    expect(phoneAppApi(new EventTarget() as unknown as Window)).toBeNull();
  });

  it("reads and checks the car app's state", () => {
    const { host } = windowWithAndroid(JSON.stringify(STATE));

    expect(phoneAppApi(host)!.read().connection).toBe("bluetooth");
  });

  it("refuses a state of the wrong shape", () => {
    const { host } = windowWithAndroid(JSON.stringify({ ...STATE, mode: "CARRIER_PIGEON" }));

    expect(() => phoneAppApi(host)!.read()).toThrow();
  });

  it("sends a change as JSON", () => {
    const { host, saved } = windowWithAndroid(JSON.stringify(STATE));

    phoneAppApi(host)!.save({ mode: "BLUETOOTH", access_point_url: "u", access_point_ssid: "s", access_point_password: null });

    expect(JSON.parse(saved[0])).toEqual({ mode: "BLUETOOTH", access_point_url: "u", access_point_ssid: "s", access_point_password: null });
  });

  it("calls a listener on each change event until it stops", () => {
    const { host } = windowWithAndroid(JSON.stringify(STATE));
    let calls = 0;
    const stop = phoneAppApi(host)!.onChange(() => (calls += 1));

    host.dispatchEvent(new Event(PHONE_APP_CHANGE_EVENT));
    stop();
    host.dispatchEvent(new Event(PHONE_APP_CHANGE_EVENT));

    expect(calls).toBe(1);
  });

  it("answers a save with what the car app's dialog reported", async () => {
    const { host } = windowWithAndroid(JSON.stringify(STATE));
    const api = phoneAppApi(host)!;

    expect(await api.saveFile("library.json", "{}")).toBe(true);
    expect(await api.saveFile("cancel.json", "{}")).toBe(false);
  });
});
