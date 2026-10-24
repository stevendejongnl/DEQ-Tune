import { beforeEach, describe, expect, it } from "vitest";
import "./device-pill.ts";
import type { DevicePill } from "./device-pill.ts";
import type { LinkState } from "./link-state.ts";

async function mount(
  properties: Partial<Pick<DevicePill, "linkState" | "layout">> = {},
): Promise<DevicePill> {
  const element = document.createElement("device-pill") as DevicePill;
  Object.assign(element, properties);
  document.body.append(element);
  await element.updateComplete;
  return element;
}

function labelOf(element: DevicePill): string {
  return element.shadowRoot!.querySelector(".device-label")?.textContent?.trim() ?? "";
}

function freshnessOf(element: DevicePill): string {
  return element.shadowRoot!.querySelector(".freshness")?.textContent?.trim() ?? "";
}

describe("device-pill", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("calls the page offline when no bridge answers", async () => {
    const element = await mount({ linkState: "no-bridge" });

    expect(freshnessOf(element)).toBe("offline");
  });

  it("calls the page live when the bridge answers, with or without the unit", async () => {
    const unitDown = await mount({ linkState: "unit-down" });
    const connected = await mount({ linkState: "connected" });

    expect(freshnessOf(unitDown)).toBe("live");
    expect(freshnessOf(connected)).toBe("live");
  });

  it("keeps the offline tag on a phone, where the label is gone", async () => {
    const element = await mount({ linkState: "no-bridge", layout: "phone" });

    expect(labelOf(element)).toBe("");
    expect(freshnessOf(element)).toBe("offline");
  });

  it("names the bridge when the bridge is what cannot be reached", async () => {
    const element = await mount({ linkState: "no-bridge" });

    expect(labelOf(element)).toBe("Bridge not reachable");
  });

  it("names the unit when the bridge answered and the unit is down", async () => {
    const element = await mount({ linkState: "unit-down" });

    expect(labelOf(element)).toBe("DEQ not connected");
  });

  it("says connected, without the firmware version", async () => {
    const element = await mount({ linkState: "connected" });

    expect(labelOf(element)).toBe("DEQ connected");
    expect(element.shadowRoot!.textContent).not.toContain("2.02");
  });

  it("drops the label on a phone until a unit is connected", async () => {
    const element = await mount({ linkState: "unit-down", layout: "phone" });

    expect(element.shadowRoot!.querySelector(".device-label")).toBeNull();
  });

  it("keeps the label on a phone once a unit is connected", async () => {
    const element = await mount({ linkState: "connected", layout: "phone" });

    expect(labelOf(element)).toBe("DEQ connected");
  });

  it("reflects the link state, so the stylesheet can colour the dot", async () => {
    // The dot's colour is a CSS rule on the host attribute, not a class
    // the template builds, so the attribute has to be there.
    const element = await mount({ linkState: "connected" });

    expect(element.getAttribute("linkstate")).toBe("connected");
  });

  it("always shows the dot, whatever the state", async () => {
    for (const linkState of ["no-bridge", "unit-down", "connected"] as LinkState[]) {
      const element = await mount({ linkState });

      expect(element.shadowRoot!.querySelector(".dot")).not.toBeNull();
    }
  });
});
