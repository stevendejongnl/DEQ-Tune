import { afterEach, describe, expect, it } from "vitest";
import "./settings-page.ts";
import type { SettingsPage, SettingsSection } from "./settings-page.ts";
import { FakeCommunityLibrary } from "./testing/fake-community-library.ts";
import { FakePhoneAppApi } from "./testing/fake-phone-app-api.ts";
import { updatedPi } from "./testing/fake-updates-api.ts";

async function mount(section: SettingsSection): Promise<SettingsPage> {
  const page = document.createElement("settings-page") as SettingsPage;
  page.community = new FakeCommunityLibrary([]);
  page.section = section;
  page.updates = updatedPi();
  document.body.append(page);
  await page.updateComplete;
  return page;
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("settings-page", () => {
  it("lists every section, and marks the one on show", async () => {
    const page = await mount("updates");
    const buttons = [...page.shadowRoot!.querySelectorAll<HTMLButtonElement>(".sections button")];

    expect(buttons.map((button) => button.textContent!.trim())).toEqual([
      "Updates",
      "Wi-Fi",
      "Backup",
      "Community",
      "System",
      "Language",
    ]);
    expect(buttons[0].getAttribute("aria-pressed")).toBe("true");
  });

  it("lists Phone app first, and only inside the car app", async () => {
    const page = document.createElement("settings-page") as SettingsPage;
    page.phoneApp = new FakePhoneAppApi();
    page.section = "phone";
    document.body.append(page);
    await page.updateComplete;
    const buttons = [...page.shadowRoot!.querySelectorAll<HTMLButtonElement>(".sections button")];

    expect(buttons[0].textContent!.trim()).toBe("Phone app");
    expect(page.shadowRoot!.querySelector(".card phone-app-settings")).not.toBeNull();
  });

  it.each([
    ["updates", "update-settings"],
    ["wifi", "wifi-settings"],
    ["backup", "library-backup"],
    ["community", "community-library"],
    ["system", "system-panel"],
    ["language", "locale-switcher"],
  ] as const)("shows %s with its own component", async (section, tag) => {
    const page = await mount(section);

    expect(page.shadowRoot!.querySelector(`.card ${tag}`)).not.toBeNull();
  });

  it("asks for another section", async () => {
    const page = await mount("updates");
    const sections: string[] = [];
    page.addEventListener("section-change", (event) =>
      sections.push((event as CustomEvent<{ section: string }>).detail.section),
    );

    page.shadowRoot!.querySelectorAll<HTMLButtonElement>(".sections button")[4].click();

    expect(sections).toEqual(["system"]);
  });
});
