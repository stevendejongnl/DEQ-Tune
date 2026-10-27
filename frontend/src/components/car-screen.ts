import { html, LitElement, nothing, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { ActiveProfileDto, AudioStateDto, EqualizerDto, ProfileDto } from "../dto/profile.dto.ts";
import { MAX_GAIN_DB } from "../eq-curve.ts";
import { equalizerName } from "../i18n/equalizer-names.ts";
import type { Locale } from "../i18n/locale.ts";
import { localizedProfileName } from "../i18n/preset-names.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import { VOLUME_MAX_DB, VOLUME_MIN_DB } from "./audio-controls.ts";
import { busyStyles } from "./busy.styles.ts";
import { carScreenStyles } from "./car-screen.styles.ts";

export type CarScreenTab = "profiles" | "equalizers" | "audio";

/** One tap on − or + moves the volume by this much, as the old car
 * folders did. */
export const VOLUME_STEP_DB = 2;

/** The car profiles to offer: the person's own, and the starred ones. The
 * sidebar shows the same two sets. */
function shownProfiles(profiles: readonly ProfileDto[]): ProfileDto[] {
  return profiles.filter((profile) => profile.source === "custom" || profile.favorite);
}

/** The EQs to offer: the starred ones and the person's own, as the EQ
 * panel shows them. */
function shownEqualizers(equalizers: readonly EqualizerDto[]): EqualizerDto[] {
  return equalizers.filter((equalizer) => equalizer.favorite || equalizer.source === "custom");
}

/** A small picture of an EQ's 13 gains, so a driver knows a tile at a glance. */
function renderCurve(gains: readonly number[]): TemplateResult {
  const width = 60;
  const height = 20;
  const points = gains
    .map((gain, band) => {
      const x = gains.length < 2 ? 0 : (band / (gains.length - 1)) * width;
      const y = height / 2 - (gain / MAX_GAIN_DB) * (height / 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return html`
    <svg class="curve" viewBox="0 0 ${width} ${height}" aria-hidden="true">
      <line x1="0" y1=${height / 2} x2=${width} y2=${height / 2} class="zero" />
      <polyline points=${points} />
    </svg>
  `;
}

/**
 * The web app on the car screen: big tiles to pick a car profile and an
 * EQ, and the volume. Android Auto gives the car app a display of about
 * 650 × 370 CSS pixels, so this screen shows one tab at a time, in
 * landscape.
 *
 * It holds no edit, and it has no way to the full app. The car screen is
 * small, and a driver uses it. The EQ chart and the speaker settings stay
 * on the phone and the laptop. It shows no notice either: no release notes
 * and no update offer. A notice would cover the tiles while the car drives.
 *
 * The tabs sit on the left, on the driver's side of a left-hand-drive car.
 *
 * Presentational, like the other panels. It emits `activate-profile`
 * ({ id }), `activate-equalizer` ({ id }, `null` for none),
 * `volume-change` ({ volumeDb }), `mute-change` ({ muted }) and
 * `tab-change` ({ tab }), and app-root does the talking. app-root also puts
 * its link status into the `status` slot.
 */
@customElement("car-screen")
export class CarScreen extends LitElement {
  static override styles = [carScreenStyles, busyStyles];

  @property({ type: String }) locale: Locale = "en";
  @property({ attribute: false }) profiles: readonly ProfileDto[] = [];
  @property({ attribute: false }) equalizers: readonly EqualizerDto[] = [];
  @property({ attribute: false }) activeProfile: ActiveProfileDto | null = null;
  /** True while a profile change waits on the Pi. */
  @property({ type: Boolean }) activatingProfile = false;
  @property({ attribute: false }) activatingEqualizer: { id: number | null } | null = null;
  @property({ attribute: false }) audioState: AudioStateDto | null = null;
  @property({ type: Boolean }) audioBusy = false;
  @property({ type: Boolean }) connected = false;

  @state() private tab: CarScreenTab = "profiles";
  /** The profile tile that the person tapped last, for its loader. */
  @state() private tappedProfileId: number | null = null;

  override render() {
    const strings = uiStrings(this.locale);
    return html`
      ${this.renderBar(strings)}
      <div class="body">
        ${this.renderTabs(strings)}
        <section class="content">${this.renderTabContent(strings)}</section>
      </div>
    `;
  }

  /** What plays now, and the link. */
  private renderBar(strings: UiStrings): TemplateResult {
    return html`
      <header class="bar">
        <div class="now-playing">
          <span class="now-profile">${this.activeProfileName(strings)}</span>
          <span class="now-equalizer">${this.activeEqualizerName(strings)}</span>
        </div>
        <slot name="status"></slot>
      </header>
    `;
  }

  private activeProfileName(strings: UiStrings): string {
    const activeId = this.activeProfile?.profile_id ?? null;
    const active = this.profiles.find((profile) => profile.id === activeId);
    return active === undefined ? strings.carScreenNoActiveProfile : localizedProfileName(active, this.locale);
  }

  private activeEqualizerName(strings: UiStrings): string {
    const activeId = this.activeProfile?.equalizer_id ?? null;
    const active = this.equalizers.find((equalizer) => equalizer.id === activeId);
    return active === undefined ? strings.noEqualizer : equalizerName(active, this.locale);
  }

  private renderTabs(strings: UiStrings): TemplateResult {
    const tabs: ReadonlyArray<{ id: CarScreenTab; label: string }> = [
      { id: "profiles", label: strings.pageCar },
      { id: "equalizers", label: strings.tabEq },
      { id: "audio", label: strings.audioTitle },
    ];
    return html`
      <nav class="tabs">
        ${tabs.map(
          (tab) => html`
            <button type="button" class="tab" data-tab=${tab.id} aria-pressed=${this.tab === tab.id}
              @click=${() => this.selectTab(tab.id)}>
              ${tab.label}
            </button>
          `,
        )}
      </nav>
    `;
  }

  /** app-root reads the unit only while the Audio tab is open. */
  private selectTab(tab: CarScreenTab): void {
    this.tab = tab;
    this.dispatchEvent(new CustomEvent("tab-change", { detail: { tab } }));
  }

  /** Picks the content of the open tab. */
  private renderTabContent(strings: UiStrings): TemplateResult {
    if (this.tab === "equalizers") {
      return this.renderEqualizers(strings);
    }
    if (this.tab === "audio") {
      return this.renderAudio(strings);
    }
    return this.renderProfiles(strings);
  }

  private renderProfiles(strings: UiStrings): TemplateResult {
    const profiles = shownProfiles(this.profiles);
    if (profiles.length === 0) {
      return html`<p class="empty">${strings.carScreenNoProfiles}</p>`;
    }
    const activeId = this.activeProfile?.profile_id ?? null;
    return html`
      <div class="tiles">
        ${profiles.map((profile) => {
          const selected = profile.id === activeId;
          return html`
            <button type="button" class="tile ${selected ? "selected" : ""}" data-profile=${profile.id}
              aria-pressed=${selected}
              aria-busy=${this.activatingProfile && this.tappedProfileId === profile.id}
              @click=${() => this.activateProfile(profile.id)}>
              <span class="tile-name">${localizedProfileName(profile, this.locale)}</span>
            </button>
          `;
        })}
      </div>
    `;
  }

  private activateProfile(id: number): void {
    this.tappedProfileId = id;
    this.dispatchEvent(new CustomEvent("activate-profile", { detail: { id } }));
  }

  private renderEqualizers(strings: UiStrings): TemplateResult {
    return html`
      <div class="tiles">
        ${this.renderEqualizerTile(null, strings.noEqualizer, null)}
        ${shownEqualizers(this.equalizers).map((equalizer) =>
          this.renderEqualizerTile(equalizer.id, equalizerName(equalizer, this.locale), equalizer.gains),
        )}
      </div>
    `;
  }

  private renderEqualizerTile(id: number | null, name: string, gains: readonly number[] | null): TemplateResult {
    const activeId = this.activeProfile === null ? undefined : this.activeProfile.equalizer_id;
    const selected = id === activeId;
    return html`
      <button type="button" class="tile ${selected ? "selected" : ""}" data-equalizer=${id ?? "none"}
        aria-pressed=${selected}
        aria-busy=${this.activatingEqualizer !== null && this.activatingEqualizer.id === id}
        @click=${() => this.dispatchEvent(new CustomEvent("activate-equalizer", { detail: { id } }))}>
        <span class="tile-name">${name}</span>
        ${gains === null ? nothing : renderCurve(gains)}
      </button>
    `;
  }

  private renderAudio(strings: UiStrings): TemplateResult {
    const state = this.audioState;
    if (!this.connected || state === null) {
      return html`<p class="empty">${strings.carScreenNoUnit}</p>`;
    }
    return html`
      <div class="audio">
        <div class="volume">
          <button type="button" class="step" aria-label=${strings.carScreenVolumeDown}
            ?disabled=${this.audioBusy || state.volume_db <= VOLUME_MIN_DB}
            @click=${() => this.changeVolume(state.volume_db - VOLUME_STEP_DB)}>−</button>
          <output class="volume-value">${state.volume_db} dB</output>
          <button type="button" class="step" aria-label=${strings.carScreenVolumeUp}
            ?disabled=${this.audioBusy || state.volume_db >= VOLUME_MAX_DB}
            @click=${() => this.changeVolume(state.volume_db + VOLUME_STEP_DB)}>+</button>
        </div>
        <button type="button" class="mute ${state.muted ? "selected" : ""}" aria-pressed=${state.muted}
          ?disabled=${this.audioBusy}
          @click=${() => this.dispatchEvent(new CustomEvent("mute-change", { detail: { muted: !state.muted } }))}>
          ${state.muted ? strings.carScreenMuted : strings.carScreenMute}
        </button>
      </div>
    `;
  }

  private changeVolume(volumeDb: number): void {
    const clamped = Math.min(VOLUME_MAX_DB, Math.max(VOLUME_MIN_DB, volumeDb));
    this.dispatchEvent(new CustomEvent("volume-change", { detail: { volumeDb: clamped } }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "car-screen": CarScreen;
  }
}
