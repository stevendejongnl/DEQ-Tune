import { html, LitElement, type PropertyValues, type TemplateResult } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { AudioStateDto } from "../dto/profile.dto.ts";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import { audioControlsStyles } from "./audio-controls.styles.ts";

/** The wire name is what the unit speaks and what this emits, but not
 * what a driver should read. Only the three names `/options` ever
 * returns reach this map -- see `AUDIO_SOURCE_CHOICES` in
 * `backend/app/schemas.py` for why the rest are excluded. */
function sourceLabel(strings: UiStrings, name: string): string {
  switch (name) {
    case "STAND_ALONE":
      return strings.audioSourceStandAlone;
    case "CAR_SOURCE":
      return strings.audioSourceCarSource;
    case "THROUGH":
      return strings.audioSourceThrough;
    default:
      return name;
  }
}

/** The unit declares two mute states, 1 (on) and 2 (off). A real unit has
 * answered 0, which is neither, so say that rather than showing "No". */
function muteLabel(strings: UiStrings, state: AudioStateDto): string {
  if (state.muted) {
    return strings.audioMutedYes;
  }
  if (state.mute_state_wire === 1) {
    return strings.audioMutedNo;
  }
  return strings.audioMutedUnknown.replace("{wire}", String(state.mute_state_wire));
}

/**
 * What the unit is doing with sound, and the two controls that change it.
 *
 * This exists because a tuning can apply perfectly and still produce
 * silence, with nothing on screen to say why. On 2026-10-09 profiles and
 * EQ styles were applied in a car with no sound at all, and there was no
 * way to tell whether the unit was muted, near the bottom of its volume
 * range, or holding a source that plays nothing. Every one of those is
 * now visible.
 *
 * `app-root` refreshes it on a timer while the unit is linked. Each read costs
 * requests and replies over USB, unlike the header's device poll, which is
 * why that timer only runs while this panel can be seen.
 *
 * Mute is shown but cannot be set. A real unit answered SET_MUTE_STATE
 * with STATUS 0 and stayed unmuted, so a mute control here would do
 * nothing while looking like it worked -- see the note in
 * `backend/app/device_routes.py`.
 *
 * Presentational, like the other panels: it emits `volume-change`
 * ({ volumeDb }) and `audio-source-change` ({ name }), and app-root does
 * the talking.
 */
@customElement("audio-controls")
export class AudioControls extends LitElement {
  static override styles = audioControlsStyles;

  @property({ type: String }) locale: Locale = "en";
  @property({ type: Object }) state: AudioStateDto | null = null;
  @property({ type: Array }) sourceNames: readonly string[] = [];
  @property({ type: Boolean }) busy = false;
  /** False while the unit is not linked. Nothing here can reach it then, so
   * every control is off and the panel says why. */
  @property({ type: Boolean }) connected = false;

  /** True while a finger or pointer holds the volume slider. */
  private holdingSlider = false;

  /** A poll hands over a new state object every few seconds. Re-rendering
   * mid-drag would snap the thumb back to the unit's value under the
   * finger, so a state-only update waits until the slider is released. */
  protected override shouldUpdate(changed: PropertyValues): boolean {
    return !(this.holdingSlider && changed.size === 1 && changed.has("state"));
  }

  private setHolding(holding: boolean): void {
    this.holdingSlider = holding;
    if (!holding) {
      this.requestUpdate();
    }
  }

  override render() {
    const strings = uiStrings(this.locale);
    return html`
      <section class="panel">
        <div class="head">
          <h2>${strings.audioTitle}</h2>
        </div>
        ${this.state === null ? this.renderUnread(strings) : this.renderState(strings)}
      </section>
    `;
  }

  private renderUnread(strings: ReturnType<typeof uiStrings>): TemplateResult {
    return html`<p class="unread">
      ${this.connected ? strings.audioNotRead : strings.audioNotConnected}
    </p>`;
  }

  private renderState(strings: ReturnType<typeof uiStrings>): TemplateResult {
    const state = this.state as AudioStateDto;
    return html`
      <dl class="readout">
        <dt>${strings.audioSourceLabel}</dt>
        <dd>${sourceLabel(strings, state.source_mode)}</dd>
        <dt>${strings.audioVolumeLabel}</dt>
        <dd>${state.volume_db} dB</dd>
        <dt>${strings.audioMutedLabel}</dt>
        <dd class=${state.muted ? "warn" : ""}>${muteLabel(strings, state)}</dd>
        <dt>${strings.audioDrivingLabel}</dt>
        <dd>${state.driving ? strings.audioDrivingYes : strings.audioDrivingNo}</dd>
      </dl>

      <label class="control">
        <span>${strings.audioVolumeLabel}</span>
        <input
          type="range"
          min="-80"
          max="10"
          step="1"
          .value=${String(state.volume_db)}
          @pointerdown=${() => this.setHolding(true)}
          @pointerup=${() => this.setHolding(false)}
          @pointercancel=${() => this.setHolding(false)}
          ?disabled=${this.busy || !this.connected}
          @change=${(event: Event) =>
            this.emit("volume-change", {
              volumeDb: Number((event.target as HTMLInputElement).value),
            })}
        />
      </label>

      <label class="control">
        <span>${strings.audioSourceLabel}</span>
        <select
          ?disabled=${this.busy || !this.connected}
          @change=${(event: Event) =>
            this.emit("audio-source-change", {
              name: (event.target as HTMLSelectElement).value,
            })}
        >
          ${this.sourceNames.map(
            (name) =>
              html`<option value=${name} ?selected=${name === state.source_mode}>
                ${sourceLabel(strings, name)}
              </option>`,
          )}
        </select>
      </label>
    `;
  }

  private emit(type: string, detail: Record<string, unknown>): void {
    this.dispatchEvent(
      new CustomEvent(type, { detail, bubbles: true, composed: true }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "audio-controls": AudioControls;
  }
}
