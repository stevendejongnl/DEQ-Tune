import { describe, expect, it } from "vitest";
import "./profile-list.ts";
import type { ProfileList } from "./profile-list.ts";
import { sampleProfile } from "../dto/testing/sample-profile.ts";
import type { ProfileDto } from "../dto/profile.dto.ts";

const factoryProfiles = [
  sampleProfile({ id: 1, car_model: "mazda_2", speaker_type: "carrozzeria" }),
  sampleProfile({ id: 2, car_model: "mazda_2", speaker_type: "general" }),
  sampleProfile({ id: 3, car_model: "mazda_cx5", speaker_type: "carrozzeria" }),
  sampleProfile({ id: 4, car_model: "mazda_cx5", speaker_type: "general" }),
];

async function mount(
  profiles: ProfileDto[] = factoryProfiles,
  selectedId: number | null = null,
): Promise<ProfileList> {
  const element = document.createElement("profile-list") as ProfileList;
  element.profiles = profiles;
  element.selectedId = selectedId;
  document.body.append(element);
  await element.updateComplete;
  return element;
}

async function mountLibrary(
  profiles: ProfileDto[] = factoryProfiles,
  selectedId: number | null = null,
): Promise<ProfileList> {
  const element = await mount(profiles, selectedId);
  (element.shadowRoot!.querySelector(".open-library") as HTMLButtonElement).click();
  await element.updateComplete;
  return element;
}

function queryModelRows(element: ProfileList): NodeListOf<HTMLLIElement> {
  return element.shadowRoot!.querySelectorAll(".model-row");
}

async function type(element: ProfileList, text: string): Promise<void> {
  const input = element.shadowRoot!.querySelector('input[type="search"]') as HTMLInputElement;
  input.value = text;
  input.dispatchEvent(new Event("input"));
  await element.updateComplete;
}

describe("profile-list", () => {
  it("shows one row per car model, not one per preset", async () => {
    const element = await mountLibrary();
    expect(queryModelRows(element)).toHaveLength(2);
  });

  it("offers a Pioneer chip and a Stock chip per model", async () => {
    const element = await mountLibrary();
    const chips = [...queryModelRows(element)[0].querySelectorAll(".chip")].map(
      (chip) => chip.textContent?.trim(),
    );
    expect(chips).toEqual(["Pioneer", "Stock"]);
  });

  it("emits select-profile with the id behind the pressed chip", async () => {
    const element = await mountLibrary();
    let detail: { id: number } | undefined;
    element.addEventListener("select-profile", (rawEvent) => {
      detail = (rawEvent as CustomEvent).detail;
    });

    const stockChip = queryModelRows(element)[0].querySelectorAll(".chip")[1] as HTMLButtonElement;
    stockChip.click();

    expect(detail).toEqual({ id: 2 });
  });

  it("marks the selected chip and its row", async () => {
    const element = await mountLibrary(factoryProfiles, 2);

    const row = queryModelRows(element)[0];
    const chips = row.querySelectorAll(".chip");
    expect(row.classList.contains("selected")).toBe(true);
    expect(chips[0].getAttribute("aria-pressed")).toBe("false");
    expect(chips[1].getAttribute("aria-pressed")).toBe("true");
  });

  it("filters the factory rows by the search text", async () => {
    const element = await mountLibrary();

    await type(element, "cx");

    expect(queryModelRows(element)).toHaveLength(1);
    expect(queryModelRows(element)[0].textContent).toContain("CX-5");
  });

  it("shows the empty hint when there are no custom profiles", async () => {
    const element = await mount();
    expect(element.shadowRoot!.querySelector(".empty")!.textContent).toContain("Start a new profile");
  });

  it("shows a custom profile with its caption", async () => {
    const element = await mount([
      ...factoryProfiles,
      sampleProfile({ id: 9, name: "My copy", source: "custom" }),
    ]);

    const row = element.shadowRoot!.querySelector(".custom-row")!;
    expect(row.textContent).toContain("My copy");
    expect(row.textContent).toContain("Your own profile");
  });

  it("keeps duplicate and delete behind the overflow button", async () => {
    const element = await mount([
      ...factoryProfiles,
      sampleProfile({ id: 9, name: "My copy", source: "custom" }),
    ]);
    expect(element.shadowRoot!.querySelector(".menu")).toBeNull();

    const more = element.shadowRoot!.querySelector(".more") as HTMLButtonElement;
    more.click();
    await element.updateComplete;

    const actions = [...element.shadowRoot!.querySelectorAll(".menu .action")].map(
      (action) => action.textContent?.trim(),
    );
    expect(actions).toEqual(["Rename", "Duplicate", "Delete"]);
  });

  it("emits duplicate-profile and delete-profile from the overflow menu", async () => {
    const element = await mount([
      ...factoryProfiles,
      sampleProfile({ id: 9, name: "My copy", source: "custom" }),
    ]);
    const events: string[] = [];
    element.addEventListener("duplicate-profile", () => events.push("duplicate"));
    element.addEventListener("delete-profile", () => events.push("delete"));

    (element.shadowRoot!.querySelector(".more") as HTMLButtonElement).click();
    await element.updateComplete;
    (element.shadowRoot!.querySelectorAll(".menu .action")[1] as HTMLButtonElement).click();
    await element.updateComplete;

    (element.shadowRoot!.querySelector(".more") as HTMLButtonElement).click();
    await element.updateComplete;
    (element.shadowRoot!.querySelectorAll(".menu .action")[2] as HTMLButtonElement).click();

    expect(events).toEqual(["duplicate", "delete"]);
  });

  it("asks for a new profile from the New profile button", async () => {
    const element = await mount();
    let asked = 0;
    element.addEventListener("create-profile", () => (asked += 1));

    (element.shadowRoot!.querySelector(".new-profile") as HTMLButtonElement).click();

    expect(asked).toBe(1);
  });

  it("offers to save the unit's tune only while a unit is connected", async () => {
    const element = await mount();
    expect(element.shadowRoot!.querySelector(".save-unit-tune")).toBeNull();

    element.unitConnected = true;
    await element.updateComplete;
    let asked = 0;
    element.addEventListener("save-unit-profile", () => (asked += 1));
    (element.shadowRoot!.querySelector(".save-unit-tune") as HTMLButtonElement).click();

    expect(asked).toBe(1);
  });

  it("renames a custom profile from the overflow menu", async () => {
    const element = await mount([
      ...factoryProfiles,
      sampleProfile({ id: 9, name: "My copy", source: "custom" }),
    ]);
    let detail: { id: number; name: string } | undefined;
    element.addEventListener("rename-profile", (rawEvent) => {
      detail = (rawEvent as CustomEvent).detail;
    });

    (element.shadowRoot!.querySelector(".more") as HTMLButtonElement).click();
    await element.updateComplete;
    (element.shadowRoot!.querySelectorAll(".menu .action")[0] as HTMLButtonElement).click();
    await element.updateComplete;

    const input = element.shadowRoot!.querySelector(".rename-input") as HTMLInputElement;
    input.value = "Night drive";
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));
    await element.updateComplete;

    expect(detail).toEqual({ id: 9, name: "Night drive" });
    expect(element.shadowRoot!.querySelector(".rename-input")).toBeNull();
  });

  it("drops the rename when Escape is pressed", async () => {
    const element = await mount([
      ...factoryProfiles,
      sampleProfile({ id: 9, name: "My copy", source: "custom" }),
    ]);
    let renames = 0;
    element.addEventListener("rename-profile", () => (renames += 1));

    (element.shadowRoot!.querySelector(".more") as HTMLButtonElement).click();
    await element.updateComplete;
    (element.shadowRoot!.querySelectorAll(".menu .action")[0] as HTMLButtonElement).click();
    await element.updateComplete;

    const input = element.shadowRoot!.querySelector(".rename-input") as HTMLInputElement;
    input.value = "Ignored";
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await element.updateComplete;

    expect(renames).toBe(0);
    expect(element.shadowRoot!.querySelector(".rename-input")).toBeNull();
  });

  it("keeps the old name when the field is emptied", async () => {
    const element = await mount([
      ...factoryProfiles,
      sampleProfile({ id: 9, name: "My copy", source: "custom" }),
    ]);
    let renames = 0;
    element.addEventListener("rename-profile", () => (renames += 1));

    (element.shadowRoot!.querySelector(".more") as HTMLButtonElement).click();
    await element.updateComplete;
    (element.shadowRoot!.querySelectorAll(".menu .action")[0] as HTMLButtonElement).click();
    await element.updateComplete;

    const input = element.shadowRoot!.querySelector(".rename-input") as HTMLInputElement;
    input.value = "   ";
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));
    await element.updateComplete;

    expect(renames).toBe(0);
  });

  it("names the factory group after the brand", async () => {
    const element = await mountLibrary();
    const labels = [...element.shadowRoot!.querySelectorAll(".group-label")].map(
      (label) => label.textContent?.replace(/\s+/g, " ").trim(),
    );
    expect(labels[0]).toBe("Factory · Mazda");
  });

  it("keeps the presets out of the sidebar until one has a star", async () => {
    const element = await mount();

    expect(queryModelRows(element)).toHaveLength(0);
    expect(element.shadowRoot!.textContent).toContain("Star a preset in the library");
  });

  it("shows a starred model in the sidebar, with both of its chips", async () => {
    const starred = factoryProfiles.map((profile) =>
      profile.car_model === "mazda_cx5" ? { ...profile, favorite: true } : profile,
    );
    const element = await mount(starred);

    const rows = queryModelRows(element);
    expect(rows).toHaveLength(1);
    expect(rows[0].textContent).toContain("CX-5");
    expect(rows[0].querySelectorAll(".chip")).toHaveLength(2);
  });

  it("stars both speaker types of a model at once", async () => {
    const element = await mountLibrary();
    let detail: { ids: number[]; favorite: boolean } | undefined;
    element.addEventListener("favorite-change", (rawEvent) => {
      detail = (rawEvent as CustomEvent).detail;
    });

    (queryModelRows(element)[1].querySelector(".star") as HTMLButtonElement).click();

    expect(detail).toEqual({ ids: [3, 4], favorite: true });
  });

  it("goes back from the library to the sidebar", async () => {
    const element = await mountLibrary();

    (element.shadowRoot!.querySelector(".library-back") as HTMLButtonElement).click();
    await element.updateComplete;

    expect(element.shadowRoot!.querySelector(".open-library")).not.toBeNull();
    expect(element.shadowRoot!.querySelector('input[type="search"]')).toBeNull();
  });
});
