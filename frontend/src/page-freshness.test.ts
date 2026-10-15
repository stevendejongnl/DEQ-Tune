import { describe, expect, it } from "vitest";
import { readPageFreshness } from "./page-freshness.ts";
import { sampleBridgeSystem } from "./components/testing/fake-bridge-system-api.ts";

describe("readPageFreshness", () => {
  it("is cached when the Pi does not answer", () => {
    expect(readPageFreshness(null, "abc")).toBe("cached");
  });

  it("is live when the Pi serves this build", () => {
    expect(readPageFreshness(sampleBridgeSystem({ frontend_build: "abc" }), "abc")).toBe("live");
  });

  it("is outdated when the Pi serves another build", () => {
    expect(readPageFreshness(sampleBridgeSystem({ frontend_build: "def" }), "abc")).toBe("outdated");
  });

  it("is live when the Pi has no build to compare", () => {
    expect(readPageFreshness(sampleBridgeSystem({ frontend_build: null }), "abc")).toBe("live");
  });
});
