import { html, LitElement, nothing, type PropertyValues, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { ApiError, type CrossoverApi } from "../api/client.ts";
import type { CrossoverDto, CrossoverFilterDto, StandardSpeakerMode } from "../dto/profile.dto.ts";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import { busyStyles } from "./busy.styles.ts";
import { crossoverPanelStyles } from "./crossover-panel.styles.ts";

/** The backend answers 409 for a speaker mode it cannot map yet. */
const UNSUPPORTED_MODE_STATUS = 409;

/** Slope 0 is Pass. 1 to 4 are the filter order, 6 dB per octave each. */
const SLOPES = [0, 1, 2, 3, 4];
const DECIBELS_PER_ORDER = 6;

type LoadProblem = "failed" | "unsupported" | null;

/** A frequency as a driver reads it: "80 Hz", "3.15 kHz". */
export function formatCutoff(hertz: number): string {
  return hertz >= 1000 ? `${hertz / 1000} kHz` : `${hertz} Hz`;
}

/**
 * The Filter screen: the unit's crossover.
 *
 * It shows each filter that the unit's speaker mode uses. The car profile
 * owns the front and rear filters, so a row for one of them only shows its
 * value. The unit keeps the others, such as the subwoofer's low pass, and
 * a change to one goes to the unit at once. The panel reads the unit when
 * `connected` turns true. It depends on a `CrossoverApi`.
 */
@customElement("crossover-panel")
export class CrossoverPanel extends LitElement {
  static override styles = [crossoverPanelStyles, busyStyles];

  @property({ attribute: false }) api: CrossoverApi | undefined;
  @property({ type: Boolean }) connected = false;
  @property({ type: String }) locale: Locale = "en";

  @state() private crossover: CrossoverDto | null = null;
  @state() private loadProblem: LoadProblem = null;
  @state() private busySpeaker: string | null = null;
  @state() private modeBusy = false;
  @state() private saveFailed = false;

  protected override updated(changed: PropertyValues<this>): void {
    if (changed.has("connected")) {
      if (this.connected) {
        void this.load();
      } else {
        this.crossover = null;
        this.loadProblem = null;
      }
    }
  }

  override render() {
    const strings = uiStrings(this.locale);
    return html`
      <section class="panel">
        <div class="panel-head">
          <h2>${strings.crossoverTitle}</h2>
          <p class="caption">${strings.crossoverIntro}</p>
        </div>
        ${this.renderBody(strings)}
      </section>
    `;
  }

  private renderBody(strings: UiStrings): TemplateResult | typeof nothing {
    if (!this.connected) {
      return html`<p class="hint">${strings.crossoverNotConnected}</p>`;
    }
    if (this.loadProblem === "unsupported") {
      return html`<p class="hint">${strings.crossoverUnsupported}</p>`;
    }
    if (this.loadProblem === "failed") {
      return html`<p class="hint" role="alert">${strings.crossoverFailed}</p>`;
    }
    if (this.crossover === null) {
      return nothing;
    }
    return html`
      ${this.renderSpeakerMode(strings, this.crossover)}
      <ul class="filters">
        ${this.crossover.filters.map((filter) => this.renderFilter(strings, filter))}
      </ul>
      ${this.saveFailed
        ? html`<p class="message" role="alert">${strings.crossoverSaveFailed}</p>`
        : nothing}
    `;
  }

  private renderSpeakerMode(strings: UiStrings, crossover: CrossoverDto): TemplateResult {
    return html`
      <label class="speaker-mode" aria-busy=${this.modeBusy}>
        <span>${strings.crossoverSpeakerModeLabel}</span>
        <select name="speaker-mode" ?disabled=${this.modeBusy || this.busySpeaker !== null}
          @change=${(changeEvent: Event) =>
            void this.changeMode((changeEvent.target as HTMLSelectElement).value as StandardSpeakerMode)}>
          ${crossover.speaker_modes.map(
            (mode) =>
              html`<option value=${mode} ?selected=${mode === crossover.speaker_mode}>
                ${speakerModeName(strings, mode)}
              </option>`,
          )}
        </select>
        <span class="hint">${strings.crossoverSpeakerModeHint}</span>
      </label>
    `;
  }

  private renderFilter(strings: UiStrings, filter: CrossoverFilterDto): TemplateResult {
    return html`
      <li class="filter" data-speaker=${filter.speaker}>
        <div class="filter-name">
          <span class="speaker">${speakerName(strings, filter.speaker)}</span>
          <span class="kind">
            ${filter.kind === "high_pass" ? strings.crossoverHighPass : strings.crossoverLowPass}
          </span>
        </div>
        ${filter.owner === "unit"
          ? this.renderEditor(strings, filter)
          : this.renderProfileValue(strings, filter)}
      </li>
    `;
  }

  private renderProfileValue(strings: UiStrings, filter: CrossoverFilterDto): TemplateResult {
    return html`
      <div class="value">
        <span class="setting">${describeFilter(strings, filter)}</span>
        <span class="hint">${strings.crossoverFromProfile}</span>
      </div>
    `;
  }

  private renderEditor(strings: UiStrings, filter: CrossoverFilterDto): TemplateResult {
    const busy = this.busySpeaker === filter.speaker;
    const disabled = this.busySpeaker !== null;
    return html`
      <div class="editor">
        <label aria-busy=${busy}>
          <span>${strings.crossoverCutoffLabel}</span>
          <select name="cutoff" ?disabled=${disabled}
            @change=${(changeEvent: Event) =>
              void this.change(filter, {
                cutoff_position: Number((changeEvent.target as HTMLSelectElement).value),
              })}>
            ${filter.cutoffs_hz.map(
              (hertz, position) =>
                html`<option value=${position} ?selected=${position === filter.cutoff_position}>
                  ${formatCutoff(hertz)}
                </option>`,
            )}
          </select>
        </label>
        <label aria-busy=${busy}>
          <span>${strings.crossoverSlopeLabel}</span>
          <select name="slope" ?disabled=${disabled}
            @change=${(changeEvent: Event) =>
              void this.change(filter, {
                slope: Number((changeEvent.target as HTMLSelectElement).value),
              })}>
            ${SLOPES.map(
              (slope) =>
                html`<option value=${slope} ?selected=${slope === filter.slope}>
                  ${slopeName(strings, slope)}
                </option>`,
            )}
          </select>
        </label>
      </div>
    `;
  }

  /** Reads the unit's crossover fresh. */
  async load(): Promise<void> {
    if (this.api === undefined) {
      return;
    }
    try {
      this.crossover = await this.api.readCrossover();
      this.loadProblem = null;
    } catch (caughtError) {
      this.crossover = null;
      this.loadProblem =
        caughtError instanceof ApiError && caughtError.status === UNSUPPORTED_MODE_STATUS
          ? "unsupported"
          : "failed";
    }
  }

  /** Sends one filter's new cutoff or slope, and shows what the unit holds. */
  async change(
    filter: CrossoverFilterDto,
    edit: { cutoff_position?: number; slope?: number },
  ): Promise<void> {
    if (this.api === undefined || filter.owner !== "unit") {
      return;
    }
    if (filter.speaker !== "subwoofer" && filter.speaker !== "rear_subwoofer") {
      return;
    }
    this.busySpeaker = filter.speaker;
    this.saveFailed = false;
    try {
      this.crossover = await this.api.writeCrossoverFilter({
        speaker: filter.speaker,
        cutoff_position: edit.cutoff_position ?? filter.cutoff_position,
        slope: edit.slope ?? filter.slope,
      });
    } catch {
      this.saveFailed = true;
      await this.showWhatTheUnitHolds();
    } finally {
      this.busySpeaker = null;
    }
  }

  /** Moves the unit to another speaker mode. The unit mutes for a moment
   * while it gets the push that goes with the new mode. */
  async changeMode(speakerMode: StandardSpeakerMode): Promise<void> {
    if (this.api === undefined || speakerMode === this.crossover?.speaker_mode) {
      return;
    }
    this.modeBusy = true;
    this.saveFailed = false;
    try {
      this.crossover = await this.api.changeSpeakerMode({ speaker_mode: speakerMode });
    } catch {
      this.saveFailed = true;
      await this.showWhatTheUnitHolds();
    } finally {
      this.modeBusy = false;
    }
  }

  /** Reads again after a refused change, so the selects show what the unit
   * holds. A failed read keeps the list as it was: the save message
   * already says what went wrong. */
  private async showWhatTheUnitHolds(): Promise<void> {
    try {
      this.crossover = await this.api!.readCrossover();
    } catch {
      // Keep the list that is on screen.
    }
  }
}

function speakerName(strings: UiStrings, speaker: CrossoverFilterDto["speaker"]): string {
  const names: Record<CrossoverFilterDto["speaker"], string> = {
    front: strings.crossoverSpeakerFront,
    rear: strings.crossoverSpeakerRear,
    rear_subwoofer: strings.crossoverSpeakerRearSubwoofer,
    subwoofer: strings.crossoverSpeakerSubwoofer,
  };
  return names[speaker];
}

function speakerModeName(strings: UiStrings, mode: StandardSpeakerMode): string {
  const names: Record<StandardSpeakerMode, string> = {
    STANDARD_FL_FR: strings.speakerModeFront,
    STANDARD_FL_FR_RL_RR: strings.speakerModeFrontRear,
    STANDARD_FL_FR_RL_RR_SW: strings.speakerModeFrontRearSubwoofer,
    STANDARD_FL_FR_RLSW_RRSW: strings.speakerModeFrontRearSubwoofers,
    STANDARD_FL_FR_SW: strings.speakerModeFrontSubwoofer,
  };
  return names[mode];
}

function slopeName(strings: UiStrings, slope: number): string {
  if (slope === 0) {
    return strings.crossoverSlopePass;
  }
  return strings.crossoverSlopeValue.replace("{slope}", String(slope * DECIBELS_PER_ORDER));
}

function describeFilter(strings: UiStrings, filter: CrossoverFilterDto): string {
  if (filter.slope === 0) {
    return strings.crossoverSlopePass;
  }
  const cutoff = filter.cutoffs_hz[filter.cutoff_position];
  return `${formatCutoff(cutoff)} · ${slopeName(strings, filter.slope)}`;
}

declare global {
  interface HTMLElementTagNameMap {
    "crossover-panel": CrossoverPanel;
  }
}
