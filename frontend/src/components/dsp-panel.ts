import { html, LitElement, type TemplateResult } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { Locale } from "../i18n/locale.ts";
import { dspPanelStyles } from "./dsp-panel.styles.ts";
import {
  type EqStyleId,
  type LiveSimulationId,
  eqStyleHasNoPioneerTranslation,
  eqStyleName,
  liveSimulationHasNoPioneerTranslation,
  liveSimulationName,
} from "../i18n/dsp-presets.ts";
import { uiStrings } from "../i18n/ui-strings.ts";

function renderLockIcon(): TemplateResult {
  return html`
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
      <rect x="2" y="5" width="8" height="6" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.2" />
      <path d="M4 5 V3.5 A2 2 0 0 1 8 3.5 V5" fill="none" stroke="currentColor" stroke-width="1.2" />
    </svg>
  `;
}

/**
 * The DEQ device's built-in EQ-style and Live-Simulation DSP presets
 * (Super Bass, Powerful, Concert hall, ...). These run on the device's
 * own firmware. This panel only tracks which one the user selects
 * locally. A selection has no effect until a unit connects (see
 * device-status.ts).
 *
 * `eqStyleIds`/`liveSimulationIds` come from the unit's own value sets
 * (`/api/device/options`), which app-root.ts reads. This panel does not
 * invent or hardcode the list of choices itself.
 *
 * It emits `eq-style-change` ({ id }), `live-simulation-change`
 * ({ id }).
 */
@customElement("dsp-panel")
export class DspPanel extends LitElement {
  static override styles = dspPanelStyles;

  @property({ type: String }) locale: Locale = "en";
  @property({ type: Array }) eqStyleIds: readonly EqStyleId[] = [];
  @property({ type: Array }) liveSimulationIds: readonly LiveSimulationId[] = [];
  @property({ type: String }) eqStyle: EqStyleId | null = null;
  @property({ type: String }) liveSimulation: LiveSimulationId | null = null;

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
          <div class="tiles">
            ${this.shownEqStyleIds.map((id) => this.renderEqStyleTile(id))}
          </div>
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

  /** The styles to offer. The DEQ's enum carries members that Pioneer
   * never shipped a label for, and the real app drops them: its picker
   * reads a label out of the app's own resources, and an entry with no
   * resource never reaches the list. Offering one here would show a
   * tile with a name this project invented, for a style no Pioneer app
   * has ever selected. */
  private get shownEqStyleIds(): EqStyleId[] {
    return this.eqStyleIds.filter((id) => !eqStyleHasNoPioneerTranslation(id));
  }

  /** The live-simulation modes to offer, dropped for the same reason. */
  private get shownLiveSimulationIds(): LiveSimulationId[] {
    return this.liveSimulationIds.filter((id) => !liveSimulationHasNoPioneerTranslation(id));
  }

  private renderEqStyleTile(id: EqStyleId): TemplateResult {
    const selected = id === this.eqStyle;
    return html`
      <button
        type="button"
        class="tile ${selected ? "selected" : ""}"
        aria-pressed=${selected}
        @click=${() => this.dispatchEvent(new CustomEvent("eq-style-change", { detail: { id } }))}
      >
        <span class="radio"></span>${eqStyleName(this.locale, id)}
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
