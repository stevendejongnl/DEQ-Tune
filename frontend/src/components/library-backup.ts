import { html, LitElement, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { TypeGuardError } from "typia";
import { ApiError, type LibraryApi } from "../api/client.ts";
import type { LibraryExportDto } from "../dto/profile.dto.ts";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import { libraryBackupStyles } from "./library-backup.styles.ts";

/** Saves a text file, and says whether it was saved. The person can cancel
 * the car app's save dialog. A browser's download gives no answer. */
export type SaveFile = (fileName: string, text: string) => Promise<boolean>;

/** Hands a text file to the browser's download, through a link with `download`. */
export async function downloadFile(fileName: string, text: string): Promise<boolean> {
  const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
  return true;
}

/** True when the client's check or the backend's refused the file's content,
 * and not when the Pi did not answer. */
function isRefusedFile(caughtError: unknown): boolean {
  if (caughtError instanceof ApiError) {
    return caughtError.status === 422;
  }
  return caughtError instanceof TypeGuardError;
}

/** The file name holds the day, so two backups do not overwrite each other. */
export function libraryFileName(now: Date): string {
  return `deq-tune-library-${now.toISOString().slice(0, 10)}.json`;
}

/**
 * Saves the person's own library to a file, and adds a file's library back.
 *
 * The Pi's database and any other copy have no sync, so this moves custom
 * profiles, custom EQs and the stars on factory presets between them. It
 * renders as the settings page's Backup section. It depends on a
 * `LibraryApi`, on a `saveFile` function and on a clock, which a test
 * replaces. It fires `library-imported` after an import added anything, so
 * app-root reads its lists again.
 */
@customElement("library-backup")
export class LibraryBackup extends LitElement {
  static override styles = libraryBackupStyles;

  @property({ attribute: false }) api: LibraryApi | undefined;
  @property({ type: String }) locale: Locale = "en";
  @property({ attribute: false }) saveFile: SaveFile = downloadFile;
  @property({ attribute: false }) now: () => Date = () => new Date();

  @state() private message = "";
  @state() private isBusy = false;

  override render() {
    const strings = uiStrings(this.locale);
    return html`
      <p class="intro">${strings.backupIntro}</p>
      <div class="actions">
        <button type="button" class="export" ?disabled=${this.isBusy} @click=${() => this.exportLibrary(strings)}>
          ${strings.backupExport}
        </button>
        <label class="import">
          ${strings.backupImport}
          <input type="file" accept="application/json,.json" ?disabled=${this.isBusy}
            @change=${(changeEvent: Event) => this.importChosenFile(changeEvent)} />
        </label>
      </div>
      ${this.message ? html`<p class="message" role="status">${this.message}</p>` : nothing}
    `;
  }

  private async exportLibrary(strings: UiStrings): Promise<void> {
    if (this.api === undefined) {
      return;
    }
    await this.busy(async () => {
      const library = await this.api!.exportLibrary();
      const saved = await this.saveFile(libraryFileName(this.now()), JSON.stringify(library, null, 2));
      if (!saved) {
        this.message = strings.backupNotSaved;
        return;
      }
      this.message = strings.backupExported
        .replace("{profiles}", String(library.profiles.length))
        .replace("{equalizers}", String(library.equalizers.length));
    }, strings);
  }

  private async importChosenFile(changeEvent: Event): Promise<void> {
    const input = changeEvent.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = "";
    if (file !== undefined) {
      await this.importText(await file.text());
    }
  }

  /** Adds the library in `text`, the content of a file that the person chose. */
  async importText(text: string): Promise<void> {
    const strings = uiStrings(this.locale);
    if (this.api === undefined) {
      return;
    }
    let library: LibraryExportDto;
    try {
      library = JSON.parse(text) as LibraryExportDto;
    } catch {
      this.message = strings.backupNotALibrary;
      return;
    }
    await this.busy(async () => {
      const result = await this.api!.importLibrary(library);
      this.message = strings.backupImported
        .replace("{profiles}", String(result.profiles_added))
        .replace("{equalizers}", String(result.equalizers_added))
        .replace("{skipped}", String(result.skipped));
      if (result.profiles_added + result.equalizers_added + result.stars_added > 0) {
        this.dispatchEvent(new CustomEvent("library-imported", { bubbles: true, composed: true }));
      }
    }, strings);
  }

  /** Runs one request, and turns its failure into words for the person. */
  private async busy(work: () => Promise<void>, strings: UiStrings): Promise<void> {
    this.isBusy = true;
    this.message = "";
    try {
      await work();
    } catch (caughtError) {
      this.message = isRefusedFile(caughtError) ? strings.backupNotALibrary : strings.backupFailed;
    } finally {
      this.isBusy = false;
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "library-backup": LibraryBackup;
  }
}
