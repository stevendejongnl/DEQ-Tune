import { describe, expect, it } from "vitest";
import "./access-point-setup.ts";
import type { AccessPointSetup } from "./access-point-setup.ts";
import { FakeWifiApi } from "./testing/fake-wifi-api.ts";

async function mount(): Promise<AccessPointSetup> {
  const element = document.createElement("access-point-setup") as AccessPointSetup;
  element.api = new FakeWifiApi({ saved: [], visible: [] }, { ssid: "deq-tune", key: "deq-tune-bridge" });
  element.ssid = "deq-tune";
  document.body.append(element);
  await element.updateComplete;
  return element;
}

function collect(element: AccessPointSetup, name: string): string[] {
  const heard: string[] = [];
  element.addEventListener(name, () => heard.push(name));
  return heard;
}

describe("access-point-setup", () => {
  it("names the network and offers Later", async () => {
    const element = await mount();
    const skips = collect(element, "access-point-setup-skipped");

    expect(element.shadowRoot!.textContent).toContain("deq-tune");
    (element.shadowRoot!.querySelector(".later") as HTMLButtonElement).click();

    expect(skips).toHaveLength(1);
  });

  it("offers Done once the form saved a key", async () => {
    const element = await mount();
    const closes = collect(element, "access-point-setup-closed");

    element.shadowRoot!.querySelector("access-point-key-form")!.dispatchEvent(
      new CustomEvent("access-point-key-saved", {
        detail: { accessPoint: { ssid: "deq-tune", uses_default_key: false } },
      }),
    );
    await element.updateComplete;
    (element.shadowRoot!.querySelector(".done") as HTMLButtonElement).click();

    expect(element.shadowRoot!.querySelector(".later")).toBeNull();
    expect(closes).toHaveLength(1);
  });
});
