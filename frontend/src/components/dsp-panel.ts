import { html, LitElement, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { Locale } from "../i18n/locale.ts";
import { dspPanelStyles } from "./dsp-panel.styles.ts";
import type { EqualizerDto } from "../dto/profile.dto.ts";
import {
  type LiveSimulationId,
  liveSimulationHasNoPioneerTranslation,
  liveSimulationName,
} from "../i18n/dsp-presets.ts";
import { equalizerName } from "../i18n/equalizer-names.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";

function renderLockIcon(): TemplateResult {
  return html`
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
      <rect x="2" y="5" width="8" height="6" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.2" />
      <path d="M4 5 V3.5 A2 2 0 0 1 8 3.5 V5" fill="none" stroke="currentColor" stroke-width="1.2" />
    </svg>
  `;
}

/**
 * The EQ that plays on top of the car profile, and the unit's
 * Live-Simulation modes.
 *
 * The EQ tiles list No EQ, the starred EQs, and the person's own EQs. A tap
 * picks the EQ. The backend adds its curve to the car profile's and pushes
 * both, now or when the DEQ connects. The Library button lists every EQ with
 * a star, the way the profile library does. The EQ area above edits the EQ
 * that plays.
 *
 * `liveSimulationIds` come from the unit's own value sets
 * (`/api/device/options`), which app-root.ts reads.
 *
 * It emits `activate-equalizer` ({ id }, `null` for none),
 * `favorite-equalizer` ({ id, favorite }) and `live-simulation-change`
 * ({ id }).
 */
@customElement("dsp-panel")
export class DspPanel extends LitElement {
  static override styles = dspPanelStyles;

  @property({ type: String }) locale: Locale = "en";
  @property({ type: Array }) equalizers: readonly EqualizerDto[] = [];
  /** The EQ that plays, `null` for none, or `undefined` before the
   * backend answered. */
  @property({ attribute: false }) activeEqualizerId: number | null | undefined = undefined;
  @property({ type: Array }) liveSimulationIds: readonly LiveSimulationId[] = [];
  @property({ type: String }) liveSimulation: LiveSimulationId | null = null;

  @state() private libraryOpen = false;

  override render() {
    const strings = uiStrings(this.locale);
    return html`
      <section class="panel">
        <div class="styles-column">
          <div class="panel-head">
            <h2>
              ${strings.soundStyleTitle}
              <span class="suffix">${strings.soundStyleSuffix}</span>
            </h2>
            <span class="lock-note">${renderLockIcon()}${strings.dspDeviceHint}</span>
          </div>
          ${this.libraryOpen ? this.renderLibrary(strings) : this.renderTiles(strings)}
        </div>
        <div class="simulation-column">
          <h2>${strings.liveSimulationTitle}</h2>
          <div class="options">
            ${this.shownLiveSimulationIds.map((id) => this.renderLiveSimulationOption(id))}
          </div>
        </div>
      </section>
    `;
  }

  /** The live-simulation modes to offer, dropped for the same reason. */
  private get shownLiveSimulationIds(): LiveSimulationId[] {
    return this.liveSimulationIds.filter((id) => !liveSimulationHasNoPioneerTranslation(id));
  }

  private renderEqualizerTile(id: number | null, name: string): TemplateResult {
    const selected = id === this.activeEqualizerId;
    return html`
      <button
        type="button"
        class="tile ${selected ? "selected" : ""}"
        aria-pressed=${selected}
        @click=${() => this.dispatchEvent(new CustomEvent("activate-equalizer", { detail: { id } }))}
      >
        <span class="radio"></span>${name}
      </button>
    `;
  }

  /** No EQ, the starred EQs, and the person's own, which show either way. */
  private renderTiles(strings: UiStrings): TemplateResult {
    const shown = this.equalizers.filter(
      (equalizer) => equalizer.favorite || equalizer.source === "custom",
    );
    return html`
      <div class="tiles">
        ${this.renderEqualizerTile(null, strings.noEqualizer)}
        ${shown.map((equalizer) =>
          this.renderEqualizerTile(equalizer.id, equalizerName(equalizer, this.locale)),
        )}
      </div>
      <button type="button" class="library-toggle" @click=${() => (this.libraryOpen = true)}>
        ${strings.library}
      </button>
    `;
  }

  /** Every EQ, each with a star. A tap on a name plays that EQ. */
  private renderLibrary(strings: UiStrings): TemplateResult {
    return html`
      <ul class="library">
        ${this.equalizers.map(
          (equalizer) => html`
            <li class="library-row ${equalizer.id === this.activeEqualizerId ? "selected" : ""}">
              <button
                type="button"
                class="library-name"
                @click=${() =>
                  this.dispatchEvent(
                    new CustomEvent("activate-equalizer", { detail: { id: equalizer.id } }),
                  )}
              >
                ${equalizerName(equalizer, this.locale)}
              </button>
              ${this.renderStar(strings, equalizer)}
            </li>
          `,
        )}
      </ul>
      <button type="button" class="library-toggle" @click=${() => (this.libraryOpen = false)}>
        ‹ ${strings.backLabel}
      </button>
    `;
  }

  private renderStar(strings: UiStrings, equalizer: EqualizerDto): TemplateResult {
    const starred = equalizer.favorite;
    return html`
      <button
        type="button"
        class="star ${starred ? "starred" : ""}"
        aria-pressed=${starred}
        aria-label=${starred ? strings.removeFavoriteLabel : strings.addFavoriteLabel}
        @click=${() =>
          this.dispatchEvent(
            new CustomEvent("favorite-equalizer", {
              detail: { id: equalizer.id, favorite: !starred },
            }),
          )}
      >
        ${starred ? "★" : "☆"}
      </button>
    `;
  }

  private renderLiveSimulationOption(id: LiveSimulationId): TemplateResult {
    const selected = id === this.liveSimulation;
    return html`
      <button
        type="button"
        class="option ${selected ? "selected" : ""}"
        aria-pressed=${selected}
        @click=${() =>
          this.dispatchEvent(new CustomEvent("live-simulation-change", { detail: { id } }))}
      >
        ${liveSimulationName(this.locale, id)}
      </button>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "dsp-panel": DspPanel;
  }
}
