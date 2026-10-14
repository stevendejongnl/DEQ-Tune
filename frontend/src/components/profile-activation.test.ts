import { describe, expect, it } from "vitest";
import "./profile-activation.ts";
import type { ProfileActivation } from "./profile-activation.ts";
import type { ActiveProfileDto, ActiveStatus } from "../dto/profile.dto.ts";

async function mount(
  active: ActiveProfileDto | null,
  options: { profileId?: number; hasDraft?: boolean } = {},
): Promise<ProfileActivation> {
  const element = document.createElement("profile-activation") as ProfileActivation;
  element.profileId = options.profileId ?? 1;
  element.active = active;
  element.hasDraft = options.hasDraft ?? false;
  document.body.append(element);
  await element.updateComplete;
  return element;
}

function activeState(overrides: Partial<ActiveProfileDto>): ActiveProfileDto {
  return {
    profile_id: null,
    status: "none",
    problem: null,
    equalizer_id: null,
    source_mode: "CAR_SOURCE",
    ...overrides,
  };
}

function activeAs(status: ActiveStatus, problem: string | null = null): ActiveProfileDto {
  return activeState({ profile_id: 1, status, problem });
}

function text(element: ProfileActivation): string {
  return element.shadowRoot!.textContent!.replace(/\s+/g, " ").trim();
}

function collectRequests(element: ProfileActivation): number[] {
  const ids: number[] = [];
  element.addEventListener("activate-profile", (rawEvent) => {
    ids.push((rawEvent as CustomEvent<{ id: number }>).detail.id);
  });
  return ids;
}

describe("profile-activation", () => {
  it("shows nothing until the backend answered", async () => {
    const element = await mount(null);
    expect(element.shadowRoot!.querySelector("button")).toBeNull();
  });

  it("offers Activate for a profile that is not the active one", async () => {
    const element = await mount(activeState({ profile_id: 7, status: "applied" }));
    const requests = collectRequests(element);

    (element.shadowRoot!.querySelector(".activate") as HTMLButtonElement).click();

    expect(requests).toEqual([1]);
  });

  it("offers Activate when no profile is active", async () => {
    const element = await mount(activeState({ profile_id: null, status: "none" }));
    expect(element.shadowRoot!.querySelector(".activate")).not.toBeNull();
  });

  it("waits for a draft to be saved, because the backend pushes the stored profile", async () => {
    const element = await mount(activeState({ profile_id: null, status: "none" }), { hasDraft: true });

    const button = element.shadowRoot!.querySelector(".activate") as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(text(element)).toContain("Save your edits first");
  });

  it("says the unit plays the active profile", async () => {
    const element = await mount(activeAs("applied"));

    expect(text(element)).toContain("Active on the DEQ");
    expect(element.shadowRoot!.querySelector("button")).toBeNull();
  });

  it("says an active profile waits for the unit to connect", async () => {
    const element = await mount(activeAs("waiting"));
    expect(text(element)).toContain("goes on when the DEQ connects");
  });

  it("offers Apply changes when the unit plays an older version", async () => {
    const element = await mount(activeAs("outdated"));
    const requests = collectRequests(element);

    (element.shadowRoot!.querySelector(".apply") as HTMLButtonElement).click();

    expect(text(element)).toContain("Apply changes");
    expect(requests).toEqual([1]);
  });

  it("says why a push failed, and offers to try again", async () => {
    const element = await mount(activeAs("failed", "the unit is not connected"));

    expect(text(element)).toContain("not on the DEQ: the unit is not connected");
    expect(element.shadowRoot!.querySelector(".apply")!.textContent).toContain("Try again");
  });
});
