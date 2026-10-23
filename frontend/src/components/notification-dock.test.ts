import { afterEach, describe, expect, it } from "vitest";
import "./notification-dock.ts";
import type { NotificationDock } from "./notification-dock.ts";

async function mount(setup: (dock: NotificationDock) => void): Promise<NotificationDock> {
  const dock = document.createElement("notification-dock") as NotificationDock;
  setup(dock);
  document.body.append(dock);
  await dock.updateComplete;
  return dock;
}

function eventsOf(dock: NotificationDock, name: string): CustomEvent[] {
  const events: CustomEvent[] = [];
  dock.addEventListener(name, (event) => events.push(event as CustomEvent));
  return events;
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("notification-dock", () => {
  it("shows nothing when there is nothing to say", async () => {
    const dock = await mount(() => {});

    expect(dock.shadowRoot!.querySelectorAll(".card")).toHaveLength(0);
  });

  it("says what is new, with the highlight and the changelog", async () => {
    const dock = await mount((element) => {
      element.whatsNewVersion = "1.16.0";
      element.highlight = "the Pi installs each new release by itself";
      element.releaseUrl = "https://example/v1.16.0";
    });
    const dismissed = eventsOf(dock, "whats-new-dismissed");

    const card = dock.shadowRoot!.querySelector(".whats-new")!;
    expect(card.textContent).toContain("Updated to 1.16.0");
    expect(card.textContent).toContain("the Pi installs each new release by itself");
    expect(card.querySelector("a")!.getAttribute("href")).toBe("https://example/v1.16.0");

    card.querySelector<HTMLButtonElement>(".primary")!.click();
    expect(dismissed[0].detail).toEqual({ version: "1.16.0" });
  });

  it("offers a waiting release with Update and Later", async () => {
    const dock = await mount((element) => {
      element.availableVersion = "1.17.0";
    });
    const requested = eventsOf(dock, "update-requested");
    const postponed = eventsOf(dock, "update-postponed");

    const card = dock.shadowRoot!.querySelector(".available")!;
    expect(card.textContent).toContain("Version 1.17.0 is available");
    card.querySelector<HTMLButtonElement>(".primary")!.click();
    card.querySelector<HTMLButtonElement>(".later")!.click();

    expect(requested).toHaveLength(1);
    expect(postponed[0].detail).toEqual({ version: "1.17.0" });
  });
});
