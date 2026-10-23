/** Picks the line that a "what's new" note shows from a release's notes.
 *
 * semantic-release writes Markdown: a heading per type, then one bullet per
 * commit, such as `* **pi:** the Pi installs each release ([2b265ca](...))`.
 * The note shows the first bullet as plain text, without the scope, the
 * links and the Markdown marks. It returns an empty string when the notes
 * have no bullet.
 */
export function releaseHighlight(notes: string): string {
  const bullet = notes
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line.startsWith("* ") || line.startsWith("- "));
  if (bullet === undefined) {
    return "";
  }
  return bullet
    .slice(2)
    .replace(/\(\[[0-9a-f]{7,}\]\([^)]*\)\)/g, "")
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/^\*\*[^*]+:\*\*\s*/, "")
    .replace(/[*_`]/g, "")
    .trim();
}
