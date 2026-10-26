import { html, LitElement, nothing, svg, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { LibraryApi } from "../api/client.ts";
import {
  CommunityLibraryClient,
  entryCar,
  entryMatches,
  entryName,
  libraryWithEntry,
  type CommunityEntry,
  type CommunityLibraryApi,
} from "../api/community-library.ts";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import { communityLibraryStyles } from "./community-library.styles.ts";
import { busyStyles } from "./busy.styles.ts";
import "./community-share-form.ts";

type KindFilter = "all" | "equalizer" | "profile";
type LoadState = "loading" | "failed" | "ready";
/** What happened when the person added one entry. */
type AddState = "adding" | "added" | "present" | "failed";

const KIND_FILTERS: readonly KindFilter[] = ["all", "equalizer", "profile"];

const CURVE_WIDTH = 120;
const CURVE_HEIGHT = 32;
const CURVE_GAIN_LIMIT_DB = 12;

/** The points of a small EQ curve, for an SVG polyline. */
export function curvePoints(gains: number[]): string {
  const step = CURVE_WIDTH / Math.max(gains.length - 1, 1);
  const middle = CURVE_HEIGHT / 2;
  return gains
    .map((gain, band) => `${(band * step).toFixed(1)},${(middle - (gain / CURVE_GAIN_LIMIT_DB) * (middle - 2)).toFixed(1)}`)
    .join(" ");
}

function kindFilterLabel(strings: UiStrings, filter: KindFilter): string {
  return {
    all: strings.communityFilterAll,
    equalizer: strings.communityFilterEqualizers,
    profile: strings.communityFilterProfiles,
  }[filter];
}

function addStateText(strings: UiStrings, addState: AddState): string {
  return {
    adding: "",
    added: strings.communityAdded,
    present: strings.communityPresent,
    failed: strings.backupFailed,
  }[addState];
}

/**
 * The community library: car profiles and EQs that other people shared on
 * GitHub, in the deq-tune-library repository.
 *
 * It renders as the settings page's Community section. It reads the index
 * when it connects, lists the entries with a filter and a search, and adds
 * one entry to the person's library through the backend's import. It
 * depends on a `LibraryApi` and on a `CommunityLibraryApi`, which a test
 * replaces. It fires `library-imported` after an entry was added, so
 * app-root reads its lists again.
 */
@customElement("community-library")
export class CommunityLibrary extends LitElement {
  static override styles = [communityLibraryStyles, busyStyles];

  @property({ attribute: false }) api: LibraryApi | undefined;
  @property({ attribute: false }) community: CommunityLibraryApi = new CommunityLibraryClient();
  @property({ type: String }) locale: Locale = "en";

  @state() private entries: CommunityEntry[] = [];
  @state() private loadState: LoadState = "loading";
  @state() private kindFilter: KindFilter = "all";
  @state() private search = "";
  @state() private addStates: ReadonlyMap<string, AddState> = new Map();

  override connectedCallback(): void {
    super.connectedCallback();
    void this.load();
  }

  async load(): Promise<void> {
    this.loadState = "loading";
    try {
      this.entries = (await this.community.readIndex()).entries;
      this.loadState = "ready";
    } catch {
      this.loadState = "failed";
    }
  }

  override render() {
    const strings = uiStrings(this.locale);
    return html`
      <p class="intro">${strings.communityIntro}</p>
      ${this.renderBody(strings)}
      <community-share-form .api=${this.api} .locale=${this.locale}></community-share-form>
    `;
  }

  /** Picks what to show for the load state. */
  private renderBody(strings: UiStrings): TemplateResult {
    switch (this.loadState) {
      case "loading":
        return html`<p class="empty" role="status">${strings.communityLoading}</p>`;
      case "failed":
        return this.renderLoadFailure(strings);
      case "ready":
        return this.renderEntries(strings);
    }
  }

  private renderLoadFailure(strings: UiStrings): TemplateResult {
    return html`
      <p class="empty" role="status">${strings.communityLoadFailed}</p>
      <button type="button" class="retry" @click=${() => this.load()}>${strings.communityRetry}</button>
    `;
  }

  private renderEntries(strings: UiStrings): TemplateResult {
    const shown = this.entries.filter(
      (entry) => (this.kindFilter === "all" || entry.kind === this.kindFilter) && entryMatches(entry, this.search),
    );
    return html`
      <div class="filters">
        <div class="kinds" role="group">
          ${KIND_FILTERS.map(
            (filter) => html`
              <button type="button" aria-pressed=${this.kindFilter === filter} @click=${() => (this.kindFilter = filter)}>
                ${kindFilterLabel(strings, filter)}
              </button>
            `,
          )}
        </div>
        <input type="search" class="search" .value=${this.search} placeholder=${strings.communitySearch}
          aria-label=${strings.communitySearch}
          @input=${(inputEvent: Event) => (this.search = (inputEvent.target as HTMLInputElement).value)} />
      </div>
      ${shown.length === 0
        ? html`<p class="empty">${strings.communityEmpty}</p>`
        : html`<ul class="entries">${shown.map((entry) => this.renderEntry(strings, entry))}</ul>`}
    `;
  }

  private renderEntry(strings: UiStrings, entry: CommunityEntry): TemplateResult {
    const addState = this.addStates.get(entry.id);
    const car = entryCar(entry);
    return html`
      <li class="entry" data-id=${entry.id}>
        <div class="entry-head">
          <span class="name">${entryName(entry)}</span>
          <span class="tag">${entry.kind === "equalizer" ? strings.communityKindEqualizer : strings.communityKindProfile}</span>
        </div>
        ${car ? html`<span class="car">${car}</span>` : nothing}
        ${entry.kind === "equalizer" ? this.renderCurve(entry.equalizer.gains) : nothing}
        <p class="description">${entry.description}</p>
        <span class="author">${strings.communityBy.replace("{author}", entry.author)}</span>
        ${entry.kind === "profile" ? html`<p class="warning">${strings.communityProfileWarning}</p>` : nothing}
        <div class="entry-actions">
          <button type="button" class="add" ?disabled=${addState === "adding" || addState === "added"}
            aria-busy=${addState === "adding"}
            @click=${() => this.addEntry(entry)}>
            ${strings.communityAdd}
          </button>
          ${addState ? html`<span class="message" role="status">${addStateText(strings, addState)}</span>` : nothing}
        </div>
      </li>
    `;
  }

  private renderCurve(gains: number[]): TemplateResult {
    return html`
      <svg class="curve" viewBox="0 0 ${CURVE_WIDTH} ${CURVE_HEIGHT}" preserveAspectRatio="none" aria-hidden="true">
        ${svg`<line class="zero" x1="0" y1=${CURVE_HEIGHT / 2} x2=${CURVE_WIDTH} y2=${CURVE_HEIGHT / 2}></line>
          <polyline points=${curvePoints(gains)}></polyline>`}
      </svg>
    `;
  }

  private async addEntry(entry: CommunityEntry): Promise<void> {
    if (this.api === undefined) {
      return;
    }
    this.setAddState(entry.id, "adding");
    try {
      const result = await this.api.importLibrary(libraryWithEntry(entry));
      const added = result.profiles_added + result.equalizers_added > 0;
      this.setAddState(entry.id, added ? "added" : "present");
      if (added) {
        this.dispatchEvent(new CustomEvent("library-imported", { bubbles: true, composed: true }));
      }
    } catch {
      this.setAddState(entry.id, "failed");
    }
  }

  private setAddState(entryId: string, addState: AddState): void {
    this.addStates = new Map(this.addStates).set(entryId, addState);
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "community-library": CommunityLibrary;
  }
}
