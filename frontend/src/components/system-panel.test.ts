import { beforeEach, describe, expect, it } from "vitest";
import "./system-panel.ts";
import { REFRESH_WHILE_OPEN_MS, type SystemPanel } from "./system-panel.ts";
import { FakeBridgeSystemApi, sampleBridgeSystem } from "./testing/fake-bridge-system-api.ts";
import { flushMicrotasks } from "../testing/flush-microtasks.ts";

/** Holds the panel's next refresh instead of running it. A test fires it. */
class ManualSchedule {
  gaps: number[] = [];
  private pending: (() => void) | null = null;

  schedule = (action: () => void, delayMs: number): unknown => {
    this.gaps.push(delayMs);
    this.pending = action;
    return this.gaps.length;
  };

  cancel = (): void => {
    this.pending = null;
  };

  get isScheduled(): boolean {
    return this.pending !== null;
  }

  fire(): void {
    const action = this.pending;
    this.pending = null;
    action?.();
  }
}

type Mounted = { element: SystemPanel; api: FakeBridgeSystemApi; schedule: ManualSchedule; reloads: number[] };

async function mountOpen(api = new FakeBridgeSystemApi(), pageBuild = "test-build"): Promise<Mounted> {
  const schedule = new ManualSchedule();
  const reloads: number[] = [];
  const element = document.createElement("system-panel") as SystemPanel;
  element.api = api;
  element.pageBuild = pageBuild;
  element.scheduleFunction = schedule.schedule;
  element.cancelFunction = schedule.cancel;
  element.reloadFunction = () => reloads.push(1);
  document.body.append(element);
  await flushMicrotasks();
  await element.updateComplete;
  return { element, api, schedule, reloads };
}

function textOf(element: SystemPanel): string {
  return element.shadowRoot!.textContent!.replace(/\s+/g, " ");
}

describe("system-panel", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("shows the Pi's board, memory, disk and network", async () => {
    const { element } = await mountOpen();

    const text = textOf(element);
    expect(text).toContain("Raspberry Pi Zero 2 W Rev 1.0");
    expect(text).toContain("300 MiB / 400 MiB · 75%");
    expect(text).toContain("8.0 GiB / 32.0 GiB · 25%");
    expect(text).toContain("192.168.4.1/24");
    expect(text).toContain("-61 dBm");
    expect(text).toContain("1h 2m");
  });

  it("shows the DEQ unit's firmware version", async () => {
    const { element } = await mountOpen();
    element.firmwareVersion = "2.02";
    await element.updateComplete;

    expect(textOf(element)).toContain("DEQ unit Firmware2.02");
  });

  it("says the unit is not connected when there is no firmware version", async () => {
    const { element } = await mountOpen();

    expect(textOf(element)).toContain("DEQ unit FirmwareDEQ not connected");
  });

  it("calls the page live when the Pi serves this build", async () => {
    const { element } = await mountOpen();

    expect(element.freshness).toBe("live");
  });

  it("says it is checking, not cached, until the first read answers", async () => {
    const api = new FakeBridgeSystemApi();
    const release = api.holdAnswers();

    const { element } = await mountOpen(api);

    expect(element.freshness).toBe("checking");
    expect(textOf(element)).toContain("State checking…");
    expect(textOf(element)).not.toContain("cached");

    release();
    await flushMicrotasks();
    await element.updateComplete;
    expect(element.freshness).toBe("live");
  });

  it("calls the page cached, and says why, when the Pi does not answer", async () => {
    const api = new FakeBridgeSystemApi();
    api.unreachable = true;

    const { element } = await mountOpen(api);

    expect(element.freshness).toBe("cached");
    expect(textOf(element)).toContain("This page is the copy that your browser cached.");
  });

  it("offers a reload when the Pi serves another build", async () => {
    const api = new FakeBridgeSystemApi();
    api.system = sampleBridgeSystem({ frontend_build: "newer-build" });
    const { element, reloads } = await mountOpen(api);

    element.shadowRoot!.querySelector<HTMLButtonElement>(".reload")!.click();

    expect(element.freshness).toBe("outdated");
    expect(reloads).toEqual([1]);
  });

  it("reads again on a timer while it is open", async () => {
    const { element, api, schedule } = await mountOpen();

    schedule.fire();
    await flushMicrotasks();
    await element.updateComplete;

    expect(api.readCount).toBe(2);
    expect(schedule.gaps).toEqual([REFRESH_WHILE_OPEN_MS, REFRESH_WHILE_OPEN_MS]);
  });

  it("stops reading once it leaves the page", async () => {
    const { element, schedule } = await mountOpen();

    element.remove();

    expect(schedule.isScheduled).toBe(false);
  });

  it("writes a dash for what a machine cannot tell", async () => {
    const api = new FakeBridgeSystemApi();
    api.system = sampleBridgeSystem({ model: null, memory_total_bytes: null, interfaces: [] });

    const { element } = await mountOpen(api);

    expect(textOf(element).replace(/ /g, "")).toContain("Board–");
    expect(textOf(element)).toContain("No network interfaces.");
  });
});
