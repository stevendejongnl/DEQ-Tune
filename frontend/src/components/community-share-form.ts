import { html, LitElement, nothing, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { LibraryApi } from "../api/client.ts";
import { COMMUNITY_CONTRIBUTING_URL } from "../api/community-library.ts";
import {
  buildShareEntry,
  newFileUrl,
  ShareError,
  type ShareChoice,
  type ShareEntry,
} from "../api/community-share.ts";
import type { LibraryExportDto } from "../dto/profile.dto.ts";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import { busyStyles } from "./busy.styles.ts";
import { communityShareFormStyles } from "./community-share-form.styles.ts";

/** Puts text on the clipboard. A test passes one that keeps the text. */
export type CopyFunction = (text: string) => Promise<void>;

const copyWithClipboard: CopyFunction = (text) => navigator.clipboard.writeText(text);

type LoadState = "closed" | "loading" | "ready" | "failed";

interface Made {
  entry: ShareEntry;
  url: string;
  prefilled: boolean;
}

/**
 * The Share form in the Community section.
 *
 * A person picks one of their own EQs or car profiles, gives their GitHub
 * name and a description, and gets the entry file that the library's
 * `tools/add_entry.py` would write. A link then opens GitHub's new-file
 * page in the library repository, with the file filled in. GitHub offers
 * a fork and a pull request, so the person needs no git and no uv. An
 * entry too long for a URL comes as text to copy instead.
 *
 * It reads the person's items from the backup export, the same data a
 * backup file holds. It depends on a `LibraryApi` and a `CopyFunction`.
 */
@customElement("community-share-form")
export class CommunityShareForm extends LitElement {
  static override styles = [communityShareFormStyles, busyStyles];

  @property({ attribute: false }) api: LibraryApi | undefined;
  @property({ type: String }) locale: Locale = "en";
  @property({ attribute: false }) copyText: CopyFunction = copyWithClipboard;

  @state() private loadState: LoadState = "closed";
  @state() private library: LibraryExportDto | null = null;
  @state() private choiceKey = "";
  @state() private author = "";
  @state() private description = "";
  @state() private brand = "";
  @state() private model = "";
  @state() private invalid = false;
  @state() private made: Made | null = null;
  @state() private copied = false;

  override render() {
    const strings = uiStrings(this.locale);
    if (this.loadState === "closed") {
      return html`
        <button type="button" class="open" @click=${() => void this.open()}>
          ${strings.communityContribute}
        </button>
      `;
    }
    return html`
      <section class="share">
        <h3>${strings.communityContribute}</h3>
        ${this.renderBody(strings)}
        <p class="hint">
          <a href=${COMMUNITY_CONTRIBUTING_URL} target="_blank" rel="noopener">${strings.communityShareGuide}</a>
        </p>
      </section>
    `;
  }

  private renderBody(strings: UiStrings): TemplateResult {
    switch (this.loadState) {
      case "loading":
        return html`<p class="hint" role="status" aria-busy="true">${strings.communityLoading}</p>`;
      case "failed":
        return html`<p class="message" role="alert">${strings.communityShareFailed}</p>`;
      default:
        return this.made === null ? this.renderForm(strings) : this.renderMade(strings, this.made);
    }
  }

  private renderForm(strings: UiStrings): TemplateResult {
    const library = this.library!;
    if (library.equalizers.length === 0 && library.profiles.length === 0) {
      return html`<p class="hint">${strings.communityShareNothing}</p>`;
    }
    const profile = this.chosenProfile();
    return html`
      <form @submit=${(submitEvent: Event) => this.make(submitEvent)}>
        <label>
          <span>${strings.communityShareItem}</span>
          <select name="item" @change=${(changeEvent: Event) => this.pick((changeEvent.target as HTMLSelectElement).value)}>
            ${library.equalizers.length > 0
              ? html`<optgroup label=${strings.communityShareEqualizers}>
                  ${library.equalizers.map((equalizer) =>
                    this.renderOption(choiceKey({ kind: "equalizer", name: equalizer.name }), equalizer.name),
                  )}
                </optgroup>`
              : nothing}
            ${library.profiles.length > 0
              ? html`<optgroup label=${strings.communityShareProfiles}>
                  ${library.profiles.map((one) => this.renderOption(choiceKey({ kind: "profile", name: one.name }), one.name))}
                </optgroup>`
              : nothing}
          </select>
        </label>
        <label>
          <span>${strings.communityShareAuthor}</span>
          <input name="author" autocomplete="username" .value=${this.author}
            @input=${(inputEvent: Event) => (this.author = (inputEvent.target as HTMLInputElement).value)} />
        </label>
        <label>
          <span>${strings.communityShareDescription}</span>
          <textarea name="description" rows="3" .value=${this.description}
            @input=${(inputEvent: Event) => (this.description = (inputEvent.target as HTMLTextAreaElement).value)}></textarea>
          <span class="hint">${strings.communityShareDescriptionHint}</span>
        </label>
        ${profile !== undefined && profile.brand_name === null
          ? this.renderTextField(strings.communityShareBrand, "brand", this.brand, (value) => (this.brand = value))
          : nothing}
        ${profile !== undefined && profile.car_model === null
          ? this.renderTextField(strings.communityShareModel, "model", this.model, (value) => (this.model = value))
          : nothing}
        ${this.invalid ? html`<p class="message" role="alert">${strings.communityShareInvalid}</p>` : nothing}
        <button type="submit" class="make">${strings.communityShareMake}</button>
      </form>
    `;
  }

  private renderOption(key: string, label: string): TemplateResult {
    return html`<option value=${key} ?selected=${key === this.choiceKey}>${label}</option>`;
  }

  private renderTextField(label: string, name: string, value: string, set: (value: string) => void): TemplateResult {
    return html`
      <label>
        <span>${label}</span>
        <input name=${name} .value=${value} @input=${(inputEvent: Event) => set((inputEvent.target as HTMLInputElement).value)} />
      </label>
    `;
  }

  private renderMade(strings: UiStrings, made: Made): TemplateResult {
    if (made.prefilled) {
      return html`
        <p class="steps">${strings.communityShareStepsPrefilled}</p>
        <a class="github" href=${made.url} target="_blank" rel="noopener">${strings.communityShareOpenGithub}</a>
      `;
    }
    return html`
      <p class="steps">${strings.communityShareStepsPaste}</p>
      <textarea class="entry" readonly rows="8" .value=${made.entry.content}></textarea>
      <div class="actions">
        <button type="button" class="copy" @click=${() => void this.copy(made.entry.content)}>
          ${this.copied ? strings.communityShareCopied : strings.communityShareCopy}
        </button>
        <a class="github" href=${made.url} target="_blank" rel="noopener">${strings.communityShareOpenGithub}</a>
      </div>
    `;
  }

  /** Reads the person's own items, and shows the form. */
  async open(): Promise<void> {
    if (this.api === undefined) {
      return;
    }
    this.loadState = "loading";
    try {
      this.library = await this.api.exportLibrary();
      const first =
        this.library.equalizers[0] !== undefined
          ? choiceKey({ kind: "equalizer", name: this.library.equalizers[0].name })
          : this.library.profiles[0] !== undefined
            ? choiceKey({ kind: "profile", name: this.library.profiles[0].name })
            : "";
      this.choiceKey = first;
      this.loadState = "ready";
    } catch {
      this.loadState = "failed";
    }
  }

  pick(key: string): void {
    this.choiceKey = key;
    this.invalid = false;
  }

  setDetails(details: { author?: string; description?: string; brand?: string; model?: string }): void {
    this.author = details.author ?? this.author;
    this.description = details.description ?? this.description;
    this.brand = details.brand ?? this.brand;
    this.model = details.model ?? this.model;
  }

  /** Builds the entry from the form. A missing field shows a message. */
  make(submitEvent?: Event): void {
    submitEvent?.preventDefault();
    if (this.library === null) {
      return;
    }
    try {
      const entry = buildShareEntry(this.library, parseChoiceKey(this.choiceKey), {
        author: this.author,
        description: this.description,
        brand: this.brand,
        model: this.model,
      });
      this.made = { entry, ...newFileUrl(entry) };
      this.invalid = false;
    } catch (caughtError) {
      if (!(caughtError instanceof ShareError)) {
        throw caughtError;
      }
      this.invalid = true;
    }
  }

  private async copy(text: string): Promise<void> {
    try {
      await this.copyText(text);
      this.copied = true;
    } catch {
      // The text stays selectable in the box, so a person copies it by hand.
      this.copied = false;
    }
  }

  private chosenProfile() {
    if (this.library === null || !this.choiceKey.startsWith("profile:")) {
      return undefined;
    }
    const name = parseChoiceKey(this.choiceKey).name;
    return this.library.profiles.find((profile) => profile.name === name);
  }
}

/** A choice as one select value: the kind, a colon, and the name. */
function choiceKey(choice: ShareChoice): string {
  return `${choice.kind}:${choice.name}`;
}

function parseChoiceKey(key: string): ShareChoice {
  const separator = key.indexOf(":");
  const kind = key.slice(0, separator);
  const name = key.slice(separator + 1);
  return kind === "profile" ? { kind: "profile", name } : { kind: "equalizer", name };
}

declare global {
  interface HTMLElementTagNameMap {
    "community-share-form": CommunityShareForm;
  }
}
