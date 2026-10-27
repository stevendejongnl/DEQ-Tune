import { describe, expect, it } from "vitest";
import { isCarScreenQuery } from "./car-screen-query.ts";

describe("isCarScreenQuery", () => {
  it("knows the car screen's query", () => {
    expect(isCarScreenQuery("?screen=car")).toBe(true);
    expect(isCarScreenQuery("?lang=de&screen=car")).toBe(true);
  });

  it("leaves the phone and the browser on the full app", () => {
    expect(isCarScreenQuery("")).toBe(false);
    expect(isCarScreenQuery("?screen=phone")).toBe(false);
  });
});
