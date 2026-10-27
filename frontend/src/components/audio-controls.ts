import { html, LitElement, type PropertyValues, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { AudioStateDto } from "../dto/profile.dto.ts";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import { audioControlsStyles } from "./audio-controls.styles.ts";
import type { CancelFunction, ScheduleFunction } from "./device-status.ts";

/** The unit's volume range, in dB. */
export const VOLUME_MIN_DB = -80;
export const VOLUME_MAX_DB = 10;

/** How long the slider must rest before a drag sends its value. Each send
 * is a USB write, so a drag sends a few values and not one per pixel. */
export const VOLUME_SEND_DELAY_MS = 300;

/** The wire name is what the unit speaks and what this emits, but not
 * what a driver should read. Only the three names `/options` ever
 * returns reach this map. See `AUDIO_SOURCE_CHOICES` in
 * `backend/app/schemas.py` for why the backend leaves out the rest. */
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

/** The wire carries a boolean: 1 muted, 0 playing. Any other value is
 * something no unit sent yet, so say that rather than showing "No". */
function muteLabel(strings: UiStrings, state: AudioStateDto): string {
  if (state.muted) {
    return strings.audioMutedYes;
  }
  if (state.mute_state_wire === 0) {
    return strings.audioMutedNo;
  }
  return strings.audioMutedUnknown.replace("{wire}", String(state.mute_state_wire));
}

/**
 * What the unit is doing with sound, and the two controls that change it.
 *
 * This component exists because a tuning can apply without error and
 * still produce silence, with no message on screen to say why. On 2026-10-09,
 * a session in a car applied profiles and EQ styles and got no sound at
 * all. Nobody could tell whether the unit's mute was on, its volume sat
 * near the bottom of its range, or it held a source that plays nothing.
 * The panel now shows every one of those.
 *
 * `app-root` refreshes it on a timer while the link is up. Each read
 * costs requests and replies over USB, unlike the header's device poll. So
 * that timer only runs while this panel is on screen.
 *
 * The panel shows mute but does not set it. The car screen
 * (`car-screen.ts`) has the mute button. The backend sent the wrong wire
 * values until 2026-10-15, so a real unit stayed unmuted then. See
 * `DeqSession.set_mute_state`.
 *
 * Presentational, like the other panels: it emits `volume-change`
 * ({ volumeDb }) and `audio-source-change` ({ name }), and app-root does
 * the talking. A drag shows its value at once, and sends it when the
 * slider rests for `VOLUME_SEND_DELAY_MS` or the finger lets go. It
 * depends on a schedule and a cancel function for that delay, which a
 * test replaces.
 */
@customElement("audio-controls")
export class AudioControls extends LitElement {
  static override styles = audioControlsStyles;

  @property({ type: String }) locale: Locale = "en";
  @property({ type: Object }) state: AudioStateDto | null = null;
  @property({ type: Array }) sourceNames: readonly string[] = [];
  @property({ type: Boolean }) busy = false;
  /** False while the unit is not linked. The controls cannot reach it
   * then, so each one is off and the panel says why. */
  @property({ type: Boolean }) connected = false;
  /** False while the Pi itself does not answer. The unit may still be up,
   * so the panel must not say that the unit is down. */
  @property({ type: Boolean }) bridgeReachable = true;

  @property({ attribute: false }) scheduleFunction: ScheduleFunction = (action, delayMs) =>
    setTimeout(action, delayMs);
  @property({ attribute: false }) cancelFunction: CancelFunction = (handle) =>
    clearTimeout(handle as ReturnType<typeof setTimeout>);

  /** True while a finger or pointer holds the volume slider. */
  private holdingSlider = false;
  /** The value under the finger, shown before the unit confirms it. */
  @state() private draftVolumeDb: number | null = null;
  private sendHandle: unknown = null;
  private lastSentVolumeDb: number | null = null;

  /** A poll hands over a new state object every few seconds. Re-rendering
   * mid-drag would snap the thumb back to the last polled value under the
   * finger, so a state-only update waits until the user releases the slider. */
  protected override shouldUpdate(changed: PropertyValues): boolean {
    return !(this.holdingSlider && changed.size === 1 && changed.has("state"));
  }

  private setHolding(holding: boolean): void {
    this.holdingSlider = holding;
    if (!holding) {
      this.requestUpdate();
    }
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    this.cancelSend();
  }

  /** A newly polled state replaces the draft once nothing waits to send. */
  protected override willUpdate(changed: PropertyValues): void {
    if (changed.has("state") && !this.holdingSlider && this.sendHandle === null) {
      this.draftVolumeDb = null;
    }
  }

  private shownVolumeDb(state: AudioStateDto): number {
    return this.draftVolumeDb ?? state.volume_db;
  }

  /** The slider moved: show the value, and send it once the slider rests. */
  private dragVolume(volumeDb: number): void {
    this.draftVolumeDb = volumeDb;
    this.cancelSend();
    this.sendHandle = this.scheduleFunction(() => {
      this.sendHandle = null;
      this.sendVolume(volumeDb);
    }, VOLUME_SEND_DELAY_MS);
  }

  /** The finger let go, or a step button: send now. */
  private commitVolume(volumeDb: number): void {
    this.draftVolumeDb = volumeDb;
    this.cancelSend();
    this.sendVolume(volumeDb);
  }

  private stepVolume(state: AudioStateDto, stepDb: number): void {
    const next = Math.min(VOLUME_MAX_DB, Math.max(VOLUME_MIN_DB, this.shownVolumeDb(state) + stepDb));
    this.commitVolume(next);
  }

  private sendVolume(volumeDb: number): void {
    if (volumeDb === this.lastSentVolumeDb) {
      return;
    }
    this.lastSentVolumeDb = volumeDb;
    this.emit("volume-change", { volumeDb });
  }

  private cancelSend(): void {
    if (this.sendHandle !== null) {
      this.cancelFunction(this.sendHandle);
      this.sendHandle = null;
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
    return html`<p class="unread">${this.unreadReason(strings)}</p>`;
  }

  private unreadReason(strings: UiStrings): string {
    if (this.connected) {
      return strings.audioNotRead;
    }
    return this.bridgeReachable ? strings.audioNotConnected : strings.audioBridgeUnreachable;
  }

  private renderState(strings: ReturnType<typeof uiStrings>): TemplateResult {
    const state = this.state as AudioStateDto;
    const off = !this.connected;
    const volumeDb = this.shownVolumeDb(state);
    const fill = ((volumeDb - VOLUME_MIN_DB) / (VOLUME_MAX_DB - VOLUME_MIN_DB)) * 100;
    return html`
      <div class="volume">
        <span class="label">${strings.audioVolumeLabel}</span>
        <div class="stepper">
          <button type="button" class="step" aria-label=${strings.audioVolumeDown} ?disabled=${off}
            @click=${() => this.stepVolume(state, -1)}>−</button>
          <output class="volume-readout">${volumeDb} <span class="unit">dB</span></output>
          <button type="button" class="step" aria-label=${strings.audioVolumeUp} ?disabled=${off}
            @click=${() => this.stepVolume(state, 1)}>+</button>
        </div>
        <input
          type="range"
          min=${VOLUME_MIN_DB}
          max=${VOLUME_MAX_DB}
          step="1"
          style="--fill: ${fill}%"
          aria-label=${strings.audioVolumeLabel}
          .value=${String(volumeDb)}
          ?disabled=${off}
          @pointerdown=${() => this.setHolding(true)}
          @pointerup=${() => this.setHolding(false)}
          @pointercancel=${() => this.setHolding(false)}
          @input=${(event: Event) => this.dragVolume(Number((event.target as HTMLInputElement).value))}
          @change=${(event: Event) => this.commitVolume(Number((event.target as HTMLInputElement).value))}
        />
      </div>

      <label class="source">
        <span class="label">${strings.audioSourceLabel}</span>
        <select
          ?disabled=${this.busy || off}
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

      <dl class="readout">
        <dt>${strings.audioMutedLabel}</dt>
        <dd class=${state.muted ? "warn" : ""}>${muteLabel(strings, state)}</dd>
        <dt>${strings.audioDrivingLabel}</dt>
        <dd>${state.driving ? strings.audioDrivingYes : strings.audioDrivingNo}</dd>
      </dl>
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
