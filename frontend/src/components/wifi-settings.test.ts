import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client.ts";
import "./wifi-settings.ts";
import { isValidNetwork, type WifiSettings } from "./wifi-settings.ts";
import { FakeWifiApi } from "./testing/fake-wifi-api.ts";

function homeAndCar(): FakeWifiApi {
  return new FakeWifiApi({
    saved: [
      { ssid: "CloudSuite", connected: true },
      { ssid: "Pixel", connected: false },
    ],
    visible: [
      { ssid: "CloudSuite", signal: 79, secured: true },
      { ssid: "Neighbour", signal: 40, secured: true },
    ],
  });
}

async function mountOpen(api: FakeWifiApi, answers: boolean[] = []): Promise<WifiSettings> {
  const element = document.createElement("wifi-settings") as WifiSettings;
  element.api = api;
  element.confirmFunction = () => answers.shift() ?? false;
  document.body.append(element);
  await element.updateComplete;
  await element.load();
  await element.updateComplete;
  return element;
}

function shadow(element: WifiSettings): ShadowRoot {
  return element.shadowRoot!;
}

function savedNames(element: WifiSettings): string[] {
  return [...shadow(element).querySelectorAll(".saved .ssid")].map((name) => name.textContent ?? "");
}

function forgetButton(element: WifiSettings, ssid: string): HTMLButtonElement {
  const row = [...shadow(element).querySelectorAll(".saved li")].find(
    (item) => item.querySelector(".ssid")?.textContent === ssid,
  );
  return row!.querySelector(".forget") as HTMLButtonElement;
}

async function typeInto(element: WifiSettings, name: string, value: string): Promise<void> {
  const input = shadow(element).querySelector(`input[name=${name}]`) as HTMLInputElement;
  input.value = value;
  input.dispatchEvent(new InputEvent("input"));
  await element.updateComplete;
}

describe("wifi-settings", () => {
  it("lists the saved networks and marks the one the Pi uses", async () => {
    const element = await mountOpen(homeAndCar());

    expect(savedNames(element)).toEqual(["CloudSuite", "Pixel"]);
    expect(shadow(element).querySelector(".tag.connected")?.textContent).toBe("Connected");
  });

  it("suggests the networks in range that are not saved yet", async () => {
    const element = await mountOpen(homeAndCar());

    const suggestions = [...shadow(element).querySelectorAll("datalist option")].map(
      (option) => (option as HTMLOptionElement).value,
    );
    expect(suggestions).toEqual(["Neighbour"]);
  });

  it("saves a network, and clears the form", async () => {
    const api = homeAndCar();
    const element = await mountOpen(api);

    await typeInto(element, "ssid", "Home");
    await typeInto(element, "password", "secret-password");
    shadow(element).querySelector("form")!.requestSubmit();
    await new Promise((resolve) => setTimeout(resolve));
    await element.updateComplete;

    expect(api.savedPasswords).toEqual(["secret-password"]);
    expect(savedNames(element)).toContain("Home");
    expect((shadow(element).querySelector("input[name=ssid]") as HTMLInputElement).value).toBe("");
  });

  it("keeps Save off while the password is too short", async () => {
    const element = await mountOpen(homeAndCar());

    await typeInto(element, "ssid", "Home");
    await typeInto(element, "password", "short");

    expect((shadow(element).querySelector(".save") as HTMLButtonElement).disabled).toBe(true);
  });

  it("forgets a network that the Pi does not use, with no question", async () => {
    const element = await mountOpen(homeAndCar());

    forgetButton(element, "Pixel").click();
    await new Promise((resolve) => setTimeout(resolve));
    await element.updateComplete;

    expect(savedNames(element)).toEqual(["CloudSuite"]);
  });

  it("asks before it forgets the network the Pi uses, and keeps it on no", async () => {
    const element = await mountOpen(homeAndCar(), [false]);

    forgetButton(element, "CloudSuite").click();
    await new Promise((resolve) => setTimeout(resolve));
    await element.updateComplete;

    expect(savedNames(element)).toEqual(["CloudSuite", "Pixel"]);
  });

  it("says why when the DEQ blocks a change", async () => {
    const api = homeAndCar();
    const element = await mountOpen(api);
    api.failWith = new ApiError(409, "POST /wifi/join failed: 409");

    (shadow(element).querySelector(".join") as HTMLButtonElement).click();
    await new Promise((resolve) => setTimeout(resolve));
    await element.updateComplete;

    expect(shadow(element).querySelector(".message")?.textContent).toContain("DEQ is connected");
    expect(api.joinRequests).toBe(0);
  });

  it("says that a machine with no helper cannot change its Wi-Fi", async () => {
    const api = homeAndCar();
    api.failWith = new ApiError(503, "GET /wifi failed: 503");

    const element = await mountOpen(api);

    expect(shadow(element).querySelector(".message")?.textContent).toContain("cannot change its Wi-Fi");
  });
});

describe("isValidNetwork", () => {
  it.each([
    ["Home", "", true],
    ["Home", "12345678", true],
    ["Home", "a1".repeat(32), true],
    ["Home", "1234567", false],
    ["Home", "x".repeat(64), false],
    ["", "12345678", false],
    ["x".repeat(33), "12345678", false],
  ])("%s with %s is %s", (ssid, password, expected) => {
    expect(isValidNetwork(ssid, password)).toBe(expected);
  });

  it("shows the loader on the one Forget that runs", async () => {
    const api = homeAndCar();
    const element = await mountOpen(api);
    let release = () => {};
    api.hold = new Promise((resolve) => (release = resolve));

    forgetButton(element, "Pixel").click();
    await element.updateComplete;

    expect(forgetButton(element, "Pixel").getAttribute("aria-busy")).toBe("true");
    expect(forgetButton(element, "CloudSuite").getAttribute("aria-busy")).toBe("false");
    release();
    await new Promise((resolve) => setTimeout(resolve));
    await element.updateComplete;
    expect(shadow(element).querySelector("[aria-busy=true]")).toBeNull();
  });
});
