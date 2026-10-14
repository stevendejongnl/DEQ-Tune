import { describe, expect, it } from "vitest";
import { ApiError, DeqApiClient } from "./client.ts";
import { createFakeFetch, jsonResponse } from "./testing/fake-fetch.ts";
import { sampleProfile } from "../dto/testing/sample-profile.ts";

describe("DeqApiClient", () => {
  it("lists profiles from the configured base URL", async () => {
    const profile = sampleProfile({ id: 1, name: "Test" });
    const api = createFakeFetch(() => jsonResponse([profile]));
    const client = new DeqApiClient("/api", api.fetch);

    const profiles = await client.listProfiles();

    expect(api.calls).toEqual([
      { url: "/api/profiles", init: { method: "GET", headers: { "Content-Type": "application/json" } } },
    ]);
    expect(profiles).toEqual([profile]);
  });

  it("sends PUT with a JSON body when updating a profile", async () => {
    const profile = sampleProfile({ name: "Renamed" });
    const api = createFakeFetch(() => jsonResponse(profile));
    const client = new DeqApiClient("/api", api.fetch);

    await client.updateProfile(1, { name: "Renamed" });

    expect(api.calls[0].url).toBe("/api/profiles/1");
    expect(api.calls[0].init?.method).toBe("PUT");
    expect(api.calls[0].init?.body).toBe(JSON.stringify({ name: "Renamed" }));
  });

  it("posts the name when it saves the unit's tune", async () => {
    const profile = sampleProfile({ id: 7, name: "Car tune", source: "custom" });
    const api = createFakeFetch(() => jsonResponse(profile, 201));
    const client = new DeqApiClient("/api", api.fetch);

    const saved = await client.saveUnitProfile("Car tune");

    expect(api.calls[0].url).toBe("/api/device/profile");
    expect(api.calls[0].init?.method).toBe("POST");
    expect(api.calls[0].init?.body).toBe(JSON.stringify({ name: "Car tune" }));
    expect(saved).toEqual(profile);
  });

  it("puts the star on its own route", async () => {
    const profile = sampleProfile({ id: 3, favorite: true });
    const api = createFakeFetch(() => jsonResponse(profile));
    const client = new DeqApiClient("/api", api.fetch);

    await client.setFavorite(3, true);

    expect(api.calls[0].url).toBe("/api/profiles/3/favorite");
    expect(api.calls[0].init?.method).toBe("PUT");
    expect(api.calls[0].init?.body).toBe(JSON.stringify({ favorite: true }));
  });

  it("activates a profile with one PUT", async () => {
    const api = createFakeFetch(() => jsonResponse({ profile_id: 4, status: "waiting", problem: null, equalizer_id: null, source_mode: "CAR_SOURCE" }));
    const client = new DeqApiClient("/api", api.fetch);

    const state = await client.activateProfile(4);

    expect(api.calls[0].url).toBe("/api/active-profile");
    expect(api.calls[0].init?.method).toBe("PUT");
    expect(api.calls[0].init?.body).toBe(JSON.stringify({ profile_id: 4 }));
    expect(state.status).toBe("waiting");
  });

  it("rejects an active-profile status the app does not know", async () => {
    const api = createFakeFetch(() => jsonResponse({ profile_id: 4, status: "maybe", problem: null, equalizer_id: null, source_mode: "CAR_SOURCE" }));
    const client = new DeqApiClient("/api", api.fetch);

    await expect(client.readActiveProfile()).rejects.toThrow();
  });

  it("resolves to undefined on a 204 delete response", async () => {
    const api = createFakeFetch(() => new Response(null, { status: 204 }));
    const client = new DeqApiClient("/api", api.fetch);

    await expect(client.deleteProfile(1)).resolves.toBeUndefined();
  });

  it("throws ApiError with status on a failed request", async () => {
    const api = createFakeFetch(() => new Response("not found", { status: 404 }));
    const client = new DeqApiClient("/api", api.fetch);

    await expect(client.getProfile(999)).rejects.toMatchObject(
      new ApiError(404, "GET /profiles/999 failed: 404"),
    );
  });

  it("rejects a response that doesn't match the ProfileDto shape", async () => {
    const api = createFakeFetch(() => jsonResponse({ id: 1, name: "Incomplete" }));
    const client = new DeqApiClient("/api", api.fetch);

    await expect(client.getProfile(1)).rejects.toThrow();
  });
});
