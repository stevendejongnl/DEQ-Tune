import { beforeEach, describe, expect, it } from "vitest";
import "./device-status.ts";
import {
  POLL_WHILE_DOWN_MS,
  POLL_WHILE_UP_MS,
  type DeviceStatus,
} from "./device-status.ts";
import type { DevicePill } from "./device-pill.ts";
import { FakeBridgeSystemApi } from "./testing/fake-bridge-system-api.ts";
import { FakeDeviceApi } from "./testing/fake-device-api.ts";
import { flushMicrotasks } from "../testing/flush-microtasks.ts";

/** Holds the component's next scheduled read instead of running it.
 *
 * It records the gap the component asked for and runs the read only when
 * a test says to. `device-status` schedules through it. It depends on
 * nothing. A real timer would make these tests wait seconds.
 */
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

  /** Runs the waiting read, as a timer firing would. */
  fire(): void {
    const action = this.pending;
    this.pending = null;
    action?.();
  }
}

/** A unit whose first read stays out until the test releases it. */
class HeldReadDeviceApi extends FakeDeviceApi {
  private release: (() => void) | null = null;

  override readDevice(): ReturnType<FakeDeviceApi["readDevice"]> {
    return new Promise((resolve) => {
      this.release = () => resolve(super.readDevice());
    });
  }

  releaseRead(): void {
    this.release?.();
  }
}

async function mount(api: FakeDeviceApi, layout = "desktop"): Promise<DeviceStatus> {
  const element = document.createElement("device-status") as DeviceStatus;
  element.api = api;
  element.layout = layout as DeviceStatus["layout"];
  document.body.append(element);
  await element.updateComplete;
  // The first read of the unit happens on connect, so settle that too.
  await element.updateComplete;
  return element;
}

async function mountWithSchedule(
  api: FakeDeviceApi,
  schedule: ManualSchedule,
): Promise<DeviceStatus> {
  const element = document.createElement("device-status") as DeviceStatus;
  element.api = api;
  element.scheduleFunction = schedule.schedule;
  element.cancelFunction = schedule.cancel;
  document.body.append(element);
  await element.updateComplete;
  await element.updateComplete;
  return element;
}

/** The pill this status element rendered.
 *
 * Selecting the element and not a class: `device-pill` is a component
 * with typed properties, so a test asserts on the values it received
 * rather than on markup it happens to produce.
 */
function pillOf(element: DeviceStatus): DevicePill {
  return element.shadowRoot!.querySelector<DevicePill>("device-pill")!;
}

describe("device-status", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("offers no connect button, because the backend connects itself", async () => {
    const element = await mount(new FakeDeviceApi());

    const buttons = [...element.shadowRoot!.querySelectorAll("button")];
    expect(buttons.map((button) => button.className)).toEqual(["open-system"]);
  });

  it("opens the system dialog when a person clicks the pill", async () => {
    const element = await mount(new FakeDeviceApi().startConnected());
    const systemApi = new FakeBridgeSystemApi();
    element.systemApi = systemApi;
    await element.updateComplete;

    element.shadowRoot!.querySelector<HTMLButtonElement>(".open-system")!.click();
    await flushMicrotasks();

    expect(systemApi.readCount).toBe(1);
  });

  it("shows the unit as connected without being asked to connect", async () => {
    const element = await mount(new FakeDeviceApi().startConnected());

    expect(element.linkState).toBe("connected");
    expect(pillOf(element).linkState).toBe("connected");
  });

  it("hands the pill the unit's firmware version", async () => {
    const element = await mount(new FakeDeviceApi().startConnected());

    expect(pillOf(element).firmwareVersion).toBe("2.02");
  });

  it("says the unit is down when the bridge answers and the unit is not there", async () => {
    const element = await mount(
      new FakeDeviceApi().startWithUnitDown("the unit is not connected"),
    );

    expect(element.linkState).toBe("unit-down");
    expect(pillOf(element).linkState).toBe("unit-down");
  });

  it("says the bridge is unreachable when the request itself fails", async () => {
    const api = new FakeDeviceApi().startConnected();
    api.unreachable = true;

    const element = await mount(api);

    expect(element.linkState).toBe("no-bridge");
    expect(pillOf(element).linkState).toBe("no-bridge");
  });

  it("passes the layout down, so the pill can shorten itself", async () => {
    const element = await mount(new FakeDeviceApi(), "phone");

    expect(pillOf(element).layout).toBe("phone");
  });

  it("tells the app which link state it read", async () => {
    const api = new FakeDeviceApi().startConnected();
    const element = document.createElement("device-status") as DeviceStatus;
    const states: string[] = [];
    element.addEventListener("link-state", (event) => {
      states.push((event as CustomEvent<{ linkState: string }>).detail.linkState);
    });
    element.api = api;
    document.body.append(element);
    await element.updateComplete;
    await element.updateComplete;

    expect(states).toEqual(["connected"]);
  });
});

describe("device-status polling", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("asks again, so a unit that comes up later is noticed with no reload", async () => {
    const api = new FakeDeviceApi();
    const schedule = new ManualSchedule();
    const element = await mountWithSchedule(api, schedule);

    expect(element.linkState).toBe("unit-down");

    // The driver switches the car on. Nobody presses anything.
    api.startConnected();
    schedule.fire();
    await element.updateComplete;
    await element.updateComplete;

    expect(element.linkState).toBe("connected");
  });

  it("stops polling when it leaves the page during a read", async () => {
    const api = new HeldReadDeviceApi();
    const schedule = new ManualSchedule();
    const element = document.createElement("device-status") as DeviceStatus;
    element.api = api;
    element.scheduleFunction = schedule.schedule;
    element.cancelFunction = schedule.cancel;
    document.body.append(element);

    element.remove();
    api.releaseRead();
    await flushMicrotasks();

    expect(schedule.gaps).toEqual([]);
  });

  it("asks again after a short gap while the link is down", async () => {
    const schedule = new ManualSchedule();
    await mountWithSchedule(new FakeDeviceApi(), schedule);

    expect(schedule.gaps).toEqual([POLL_WHILE_DOWN_MS]);
  });

  it("waits longer between reads once the link is up", async () => {
    const schedule = new ManualSchedule();
    await mountWithSchedule(new FakeDeviceApi().startConnected(), schedule);

    expect(schedule.gaps).toEqual([POLL_WHILE_UP_MS]);
  });

  it("goes back to the short gap when a live link drops", async () => {
    const api = new FakeDeviceApi().startConnected();
    const schedule = new ManualSchedule();
    const element = await mountWithSchedule(api, schedule);

    api.startWithUnitDown("the link failed");
    schedule.fire();
    await element.updateComplete;
    await element.updateComplete;

    expect(schedule.gaps).toEqual([POLL_WHILE_UP_MS, POLL_WHILE_DOWN_MS]);
  });

  it("stops asking once it leaves the page", async () => {
    const schedule = new ManualSchedule();
    const element = await mountWithSchedule(
      new FakeDeviceApi().startConnected(),
      schedule,
    );

    element.remove();

    expect(schedule.isScheduled).toBe(false);
  });
});
