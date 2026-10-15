import { describe, expect, it } from "vitest";
import { formatBytes, formatDuration, usedPercent } from "./system-format.ts";

describe("formatBytes", () => {
  it("writes small sizes in whole bytes", () => {
    expect(formatBytes(512)).toBe("512 B");
  });

  it("writes one decimal below 100 of a unit", () => {
    expect(formatBytes(1536)).toBe("1.5 KiB");
  });

  it("writes whole units from 100 of a unit up", () => {
    expect(formatBytes(425000 * 1024)).toBe("415 MiB");
  });

  it("stops at the largest unit", () => {
    expect(formatBytes(2 * 1024 ** 5)).toBe("2048 TiB");
  });
});

describe("formatDuration", () => {
  it("writes minutes alone for a short uptime", () => {
    expect(formatDuration(125)).toBe("2m");
  });

  it("writes hours and minutes", () => {
    expect(formatDuration(3 * 3600 + 60)).toBe("3h 1m");
  });

  it("keeps a zero hour between days and minutes", () => {
    expect(formatDuration(86400 + 120)).toBe("1d 0h 2m");
  });
});

describe("usedPercent", () => {
  it("gives the used share", () => {
    expect(usedPercent(200, 50)).toBe(75);
  });

  it("gives 0 for an empty total", () => {
    expect(usedPercent(0, 0)).toBe(0);
  });
});
