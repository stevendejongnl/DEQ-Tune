import { describe, expect, it } from "vitest";
import { releaseHighlight } from "./release-notes.ts";

describe("releaseHighlight", () => {
  it("takes the first bullet of semantic-release's notes, as plain text", () => {
    const notes = [
      "## [1.16.0](https://github.com/example/compare/v1.15.0...v1.16.0) (2026-10-23)",
      "",
      "### Features",
      "",
      "* the Pi installs each new release by itself ([2b265ca](https://github.com/example/commit/2b265ca))",
      "* something else",
    ].join("\n");

    expect(releaseHighlight(notes)).toBe("the Pi installs each new release by itself");
  });

  it("drops a bold scope", () => {
    expect(releaseHighlight("* **pi:** a settings page")).toBe("a settings page");
  });

  it("is empty for notes with no bullet", () => {
    expect(releaseHighlight("## 1.0.0")).toBe("");
  });
});
