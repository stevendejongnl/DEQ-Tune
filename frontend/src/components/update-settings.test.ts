import { afterEach, describe, expect, it } from "vitest";
import "./update-settings.ts";
import type { UpdateSettings } from "./update-settings.ts";
import { NO_UPDATER, updatedPi } from "./testing/fake-updates-api.ts";

async function mount(setup: (element: UpdateSettings) => void): Promise<UpdateSettings> {
  const element = document.createElement("update-settings") as UpdateSettings;
  setup(element);
  document.body.append(element);
  await element.updateComplete;
  return element;
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("update-settings", () => {
  it("shows the installed and the latest release, and the history", async () => {
    const element = await mount((settings) => (settings.updates = updatedPi({ latest: "1.17.0" })));
    const text = element.shadowRoot!.textContent!.replace(/\s+/g, " ");

    expect(element.shadowRoot!.querySelector(".installed")!.textContent).toBe("1.16.0");
    expect(text).toContain("1.17.0");
    expect(text).toContain("1.15.0 → 1.16.0");
  });

  it("says when the machine has no updater", async () => {
    const element = await mount((settings) => (settings.updates = NO_UPDATER));

    expect(element.shadowRoot!.textContent).toContain("no release updater");
    expect(element.shadowRoot!.querySelector("input")).toBeNull();
  });

  it("fires automatic-change when the switch flips", async () => {
    const element = await mount((settings) => (settings.updates = updatedPi()));
    const changes: boolean[] = [];
    element.addEventListener("automatic-change", (event) =>
      changes.push((event as CustomEvent<{ automatic: boolean }>).detail.automatic),
    );

    const toggle = element.shadowRoot!.querySelector<HTMLInputElement>("input[name=automatic]")!;
    expect(toggle.checked).toBe(true);
    toggle.checked = false;
    toggle.dispatchEvent(new Event("change"));

    expect(changes).toEqual([false]);
  });

  it("fires request-update, and shows what happened", async () => {
    const element = await mount((settings) => {
      settings.updates = updatedPi();
      settings.requestState = "requested";
    });
    const requests: Event[] = [];
    element.addEventListener("request-update", (event) => requests.push(event));

    element.shadowRoot!.querySelector<HTMLButtonElement>(".check-now")!.click();

    expect(requests).toHaveLength(1);
    expect(element.shadowRoot!.querySelector(".message")!.textContent).toContain("checks for a new version");
  });

  it("says that the gadget waits for a moment with no session", async () => {
    const element = await mount((settings) => (settings.updates = updatedPi({ gadget_pending: true })));

    expect(element.shadowRoot!.textContent).toContain("waits for a moment with no DEQ session");
  });
});
