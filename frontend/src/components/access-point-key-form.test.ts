import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client.ts";
import type { AccessPointDto } from "../dto/profile.dto.ts";
import "./access-point-key-form.ts";
import { isValidAccessPointKey, type AccessPointKeyForm } from "./access-point-key-form.ts";
import { FakeWifiApi } from "./testing/fake-wifi-api.ts";

function piWithAccessPoint(): FakeWifiApi {
  return new FakeWifiApi({ saved: [], visible: [] }, { ssid: "deq-tune", key: "deq-tune-bridge" });
}

async function mount(api: FakeWifiApi): Promise<AccessPointKeyForm> {
  const element = document.createElement("access-point-key-form") as AccessPointKeyForm;
  element.api = api;
  document.body.append(element);
  await element.updateComplete;
  return element;
}

async function typeInto(element: AccessPointKeyForm, name: string, value: string): Promise<void> {
  const input = element.shadowRoot!.querySelector(`input[name=${name}]`) as HTMLInputElement;
  input.value = value;
  input.dispatchEvent(new InputEvent("input"));
  await element.updateComplete;
}

function saveButton(element: AccessPointKeyForm): HTMLButtonElement {
  return element.shadowRoot!.querySelector(".save") as HTMLButtonElement;
}

async function save(element: AccessPointKeyForm): Promise<void> {
  saveButton(element).click();
  await new Promise((resolve) => setTimeout(resolve));
  await element.updateComplete;
}

describe("access-point-key-form", () => {
  it("saves only when both fields hold the same valid key", async () => {
    const api = piWithAccessPoint();
    const element = await mount(api);

    await typeInto(element, "key", "a much better key");
    expect(saveButton(element).disabled).toBe(true);
    await typeInto(element, "repeated-key", "a much better kez");
    expect(saveButton(element).disabled).toBe(true);
    await typeInto(element, "repeated-key", "a much better key");
    expect(saveButton(element).disabled).toBe(false);

    await save(element);

    expect(api.accessPoint?.key).toBe("a much better key");
    expect(element.shadowRoot!.querySelector(".message")?.textContent).toContain("restarts now");
  });

  it("tells app-root that the key changed, out of every shadow root", async () => {
    const element = await mount(piWithAccessPoint());
    const heard: AccessPointDto[] = [];
    document.body.addEventListener("access-point-key-saved", (savedEvent) =>
      heard.push((savedEvent as CustomEvent<{ accessPoint: AccessPointDto }>).detail.accessPoint),
    );
    await typeInto(element, "key", "a much better key");
    await typeInto(element, "repeated-key", "a much better key");

    await save(element);

    expect(heard).toEqual([{ ssid: "deq-tune", uses_default_key: false }]);
  });

  it("shows the refusal when the Pi refuses the key", async () => {
    const api = piWithAccessPoint();
    const element = await mount(api);
    await typeInto(element, "key", "a much better key");
    await typeInto(element, "repeated-key", "a much better key");
    api.failWith = new ApiError(503, "no helper");

    await save(element);

    expect(element.shadowRoot!.querySelector(".message")?.textContent).not.toBe("");
    expect(api.accessPoint?.key).toBe("deq-tune-bridge");
  });

  it("refuses an empty key, which would open the network", () => {
    expect(isValidAccessPointKey("")).toBe(false);
    expect(isValidAccessPointKey("short")).toBe(false);
    expect(isValidAccessPointKey("eight ch")).toBe(true);
  });

  it("shows the loader on Save while the Pi works on the key", async () => {
    const api = piWithAccessPoint();
    let release = () => {};
    api.hold = new Promise((resolve) => (release = resolve));
    const element = await mount(api);
    await typeInto(element, "key", "a much better key");
    await typeInto(element, "repeated-key", "a much better key");

    saveButton(element).click();
    await element.updateComplete;
    expect(saveButton(element).getAttribute("aria-busy")).toBe("true");

    release();
    await new Promise((resolve) => setTimeout(resolve));
    await element.updateComplete;
    expect(saveButton(element).getAttribute("aria-busy")).toBe("false");
  });
});
