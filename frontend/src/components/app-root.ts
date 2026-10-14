import { html, LitElement, nothing, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import {
  DeqApiClient,
  type DeviceApi,
  type EqualizerApi,
  type ProfileApi,
} from "../api/client.ts";
import type {
  ActiveProfileDto,
  AudioStateDto,
  ProfileDto,
  Speaker,
  TuningDataDto,
} from "../dto/profile.dto.ts";
import { blankTuningData } from "../dto/blank-tuning.ts";
import { equalizerGains, withEqualizerGain, withSpeakerField } from "../dto/tuning-data-edits.ts";
import { browserLocaleStorage } from "../i18n/browser-locale-storage.ts";
import { type Locale, type LocaleStorage, resolveInitialLocale, saveLocale } from "../i18n/locale.ts";
import {
  localizedModelName,
  localizedProfileName,
  localizedSpeakerTypeLabel,
} from "../i18n/preset-names.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import type { LiveSimulationId } from "../i18n/dsp-presets.ts";
import { browserLayoutQuery, type AppLayout, type LayoutQuery } from "../layout-query.ts";
import { countEdits } from "../tuning-edit-count.ts";
import "./profile-list.ts";
import "./eq-editor.ts";
import "./speaker-panel.ts";
import "./bridge-notices.ts";
import "./device-status.ts";
import "./locale-switcher.ts";
import "./dsp-panel.ts";
import "./audio-controls.ts";
import "./profile-activation.ts";
import "./equalizer-editor.ts";
import { EqualizerLibraryController } from "./equalizer-library-controller.ts";
import type { LinkState } from "./link-state.ts";
import { appRootStyles } from "./app-root.styles.ts";

/** How often the audio panel re-reads the unit while it can be seen. A read
 * is four exchanges over USB, so this is slower than the header's poll. */
export const AUDIO_POLL_MS = 5000;

type ScheduleFunction = (action: () => void, delayMs: number) => unknown;
type CancelFunction = (handle: unknown) => void;

/** The four tabs of the phone layout's bottom tab bar. */
type PhoneTab = "audio" | "eq" | "car";

/** Sound holds what plays: the audio, the EQ and its library. Car holds the
 * car profile: the speakers, their timing and the car's own correction. */
type AppPage = "sound" | "car";

function resolveGlobalLanguages(): readonly string[] {
  return typeof navigator === "undefined" ? [] : navigator.languages;
}

function renderNoSelection(strings: UiStrings): TemplateResult {
  return html`<p class="empty">${strings.selectProfilePrompt}</p>`;
}

function renderWordmarkIcon(): TemplateResult {
  return html`
    <svg class="mark" width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
      <rect x="1" y="1" width="26" height="26" rx="7" fill="none" stroke="currentColor" stroke-width="1.5" />
      <path
        d="M6 17 L9 12 L12 15 L15 8 L18 16 L22 11"
        fill="none"
        stroke="currentColor"
        stroke-width="1.8"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
  `;
}

function renderProfilesToggle(strings: UiStrings, onOpen: () => void): TemplateResult {
  return html`
    <button type="button" class="profiles-toggle" @click=${onOpen}>
      <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
        <path
          d="M3 5.5h14M3 10h14M3 14.5h14"
          stroke="currentColor"
          stroke-width="1.6"
          stroke-linecap="round"
        />
      </svg>
      ${strings.profilesButton}
    </button>
  `;
}

/** The badge text: neutral for untouched factory data, and a count of
 * the edits once the user changes something. */
function editBadgeText(strings: UiStrings, editCount: number): string {
  if (editCount === 0) {
    return strings.factoryBadge;
  }
  return editCount === 1
    ? strings.editedBadgeOne
    : strings.editedBadgeMany.replace("{count}", String(editCount));
}

/**
 * Top-level page: loads profiles from the backend and wires the
 * profile sidebar, EQ editor, speaker panel, DSP and audio panels,
 * device status pill, and language switcher together.
 *
 * One shell serves three layouts. The sidebar is permanent on desktop,
 * a drawer on tablet, and a bottom sheet on the phone. The phone layout
 * also renders one tab at a time.
 *
 * `api`, `localeStorage` and `layoutQuery` default to real
 * implementations but are settable properties so tests can inject fakes
 * instead of mocking `fetch`/`navigator`/`localStorage`/`matchMedia`.
 */
@customElement("app-root")
export class AppRoot extends LitElement {
  static override styles = appRootStyles;

  @property({ attribute: false }) api: ProfileApi & DeviceApi & EqualizerApi = new DeqApiClient();
  @property({ attribute: false }) localeStorage: LocaleStorage = browserLocaleStorage;
  @property({ attribute: false }) browserLanguages: readonly string[] = resolveGlobalLanguages();
  @property({ attribute: false }) layoutQuery: LayoutQuery = browserLayoutQuery;
  /** The audio timer, injectable like `device-status`'s so a test can fire it. */
  @property({ attribute: false }) scheduleFunction: ScheduleFunction = (action, delayMs) =>
    setTimeout(action, delayMs);
  @property({ attribute: false }) cancelFunction: CancelFunction = (handle) =>
    clearTimeout(handle as ReturnType<typeof setTimeout>);

  @state() private profiles: ProfileDto[] = [];
  @state() private selectedId: number | null = null;
  @state() private locale: Locale = "en";
  @state() private liveSimulationIds: readonly LiveSimulationId[] = [];
  /** The EQ library, and the edits of the EQ that plays. */
  private readonly equalizerLibrary = new EqualizerLibraryController(this, {
    api: () => this.api,
    activeEqualizerId: () =>
      this.activeProfile === null ? undefined : this.activeProfile.equalizer_id,
    setActive: (state) => (this.activeProfile = state),
    reloadActive: () => this.loadActiveProfile(),
    newEqualizerName: () => uiStrings(this.locale).newEqualizerName,
  });
  @state() private liveSimulation: LiveSimulationId | null = null;
  @state() private profilesDrawerOpen = false;
  @state() private layout: AppLayout = "desktop";
  /** The phone opens on the audio tab: it answers "is anything audible
   * right now", the question a driver has before touching a
   * profile or an EQ band. See `audio-controls.ts` for why that question
   * had no answer before this panel existed. */
  @state() private phoneTab: PhoneTab = "audio";
  @state() private page: AppPage = "sound";
  @state() private audioState: AudioStateDto | null = null;
  @state() private audioSourceNames: readonly string[] = [];
  @state() private audioBusy = false;
  /** Whether the DEQ link is up, as `device-status` last polled it. */
  @state() private unitConnected = false;
  /** Which profile the unit plays, as the backend reports it. `null` until
   * the first read answers. */
  @state() private activeProfile: ActiveProfileDto | null = null;
  @state() private activating = false;
  /** A custom profile's newest edit that the backend does not hold yet.
   * The screen shows it at once, and `saveUnsavedEdits` sends it. */
  @state() private unsavedEdit: { profileId: number; data: TuningDataDto } | null = null;
  private savingEdits = false;

  /** Edits to a factory preset live here until the user saves them. */
  @state() private draft: TuningDataDto | null = null;

  /** `confirmDiscard` asks before the component drops a draft. It
   * defaults to the browser dialog, but a test can answer it without one. */
  @property({ attribute: false }) confirmDiscard: (question: string) => boolean = (question) =>
    typeof window === "undefined" ? true : window.confirm(question);

  private unsubscribeLayout: (() => void) | null = null;
  private audioPollHandle: unknown;

  private readonly onKeydown = (event: KeyboardEvent): void => {
    if (event.key === "Escape" && this.profilesDrawerOpen) {
      this.closeProfilesDrawer();
    }
  };

  override connectedCallback() {
    super.connectedCallback();
    this.locale = resolveInitialLocale(this.localeStorage, this.browserLanguages);
    this.layout = this.layoutQuery.current();
    this.unsubscribeLayout = this.layoutQuery.subscribe((layout) => {
      this.layout = layout;
    });
    this.loadProfiles();
    this.loadDeviceOptions();
    void this.loadActiveProfile();
    void this.equalizerLibrary.load();
    window.addEventListener("keydown", this.onKeydown);
  }

  override disconnectedCallback() {
    super.disconnectedCallback();
    window.removeEventListener("keydown", this.onKeydown);
    this.unsubscribeLayout?.();
    this.unsubscribeLayout = null;
    this.stopAudioPolling();
  }

  private get selectedProfile(): ProfileDto | undefined {
    return this.profiles.find((profile) => profile.id === this.selectedId);
  }

  private get isPhoneLayout(): boolean {
    return this.layout === "phone";
  }

  /** The data the panels show: the draft while it exists, else the
   * stored profile. */
  private get shownData(): TuningDataDto | undefined {
    const unsaved = this.unsavedEdit;
    if (unsaved !== null && unsaved.profileId === this.selectedId) {
      return unsaved.data;
    }
    return this.draft ?? this.selectedProfile?.data;
  }

  /** The factory data the edits compare against. */
  private get factoryData(): TuningDataDto | undefined {
    const profile = this.selectedProfile;
    if (profile === undefined) {
      return undefined;
    }
    if (profile.source === "factory") {
      return profile.data;
    }
    return this.profiles.find(
      (candidate) =>
        candidate.source === "factory" &&
        candidate.car_model === profile.car_model &&
        candidate.speaker_type === profile.speaker_type,
    )?.data;
  }

  private get editCount(): number {
    const shown = this.shownData;
    const factory = this.factoryData;
    return shown === undefined || factory === undefined ? 0 : countEdits(shown, factory);
  }

  /** The factory curve to draw behind your own. A factory profile
   * compares against itself. A custom profile compares against the
   * factory profile for the same car model and speaker type. */
  private get factoryGains(): number[] {
    const factory = this.factoryData;
    return factory === undefined ? [] : equalizerGains(factory);
  }

  override render() {
    const strings = uiStrings(this.locale);
    return html`
      ${this.renderProfilesDrawer(strings)}
      <div class="content">
        <header>
          <div class="header-start">
            ${this.isPhoneLayout
              ? html`<div class="wordmark">${renderWordmarkIcon()}</div>`
              : html`
                  ${renderProfilesToggle(strings, () => this.openProfilesDrawer())}
                  <div class="wordmark">${renderWordmarkIcon()}<h1>DEQ Tune</h1></div>
                `}
            ${this.isPhoneLayout ? this.renderPhoneProfileButton(strings) : nothing}
          </div>
          ${this.isPhoneLayout ? nothing : this.renderPageSwitch(strings)}
          <div class="header-controls">
            ${this.isPhoneLayout
              ? nothing
              : html`${this.renderLocaleSwitcher()}<span class="header-divider"></span>`}
            <bridge-notices .api=${this.api} .locale=${this.locale}></bridge-notices>
            <device-status
              .api=${this.api}
              .locale=${this.locale}
              .layout=${this.layout}
              @link-state=${(linkEvent: CustomEvent<{ linkState: LinkState }>) =>
                this.onLinkState(linkEvent.detail.linkState)}
            ></device-status>
          </div>
        </header>
        <main>
          ${this.isPhoneLayout ? this.renderPhonePanels(strings) : this.renderWidePanels(strings)}
        </main>
        ${this.isPhoneLayout ? this.renderSaveBar(strings) : nothing}
        ${this.isPhoneLayout ? this.renderTabBar(strings) : nothing}
      </div>
    `;
  }

  private renderProfilesDrawer(strings: UiStrings): TemplateResult {
    return html`
      ${this.profilesDrawerOpen
        ? html`<div class="drawer-backdrop" @click=${() => this.closeProfilesDrawer()}></div>`
        : null}
      <aside class="drawer ${this.profilesDrawerOpen ? "open" : ""}">
        <div class="grab-handle"></div>
        <div class="sidebar-wordmark">${renderWordmarkIcon()}<h1>DEQ Tune</h1></div>
        <div class="drawer-header">
          <button
            type="button"
            class="drawer-close"
            aria-label=${strings.closeLabel}
            @click=${() => this.closeProfilesDrawer()}
          >
            ×
          </button>
        </div>
        ${this.isPhoneLayout
          ? html`<div class="sheet-locale">${this.renderLocaleSwitcher()}</div>`
          : nothing}
        <profile-list
          .profiles=${this.profiles}
          .selectedId=${this.selectedId}
          .locale=${this.locale}
          .unitConnected=${this.unitConnected}
          .activeProfileId=${this.activeProfile?.profile_id ?? null}
          @select-profile=${(selectEvent: CustomEvent<{ id: number }>) =>
            this.selectProfile(selectEvent.detail.id)}
          @duplicate-profile=${(duplicateEvent: CustomEvent<{ id: number }>) =>
            this.duplicateProfile(duplicateEvent.detail.id)}
          @delete-profile=${(deleteEvent: CustomEvent<{ id: number }>) =>
            this.deleteProfile(deleteEvent.detail.id)}
          @rename-profile=${(renameEvent: CustomEvent<{ id: number; name: string }>) =>
            this.renameProfile(renameEvent.detail.id, renameEvent.detail.name)}
          @create-profile=${() => this.createProfile()}
          @save-unit-profile=${() => this.saveUnitProfile()}
          @favorite-change=${(favoriteEvent: CustomEvent<{ ids: number[]; favorite: boolean }>) =>
            this.changeFavorite(favoriteEvent.detail.ids, favoriteEvent.detail.favorite)}
        ></profile-list>
      </aside>
    `;
  }

  /** The breadcrumb and the model name, with the edit badge and the
   * save actions. A custom profile shows the name the user typed, and
   * no breadcrumb. It carries the car model of the preset the user
   * duplicated, but that field says which car the tuning suits rather
   * than the profile's name. */
  private renderHeadingRow(strings: UiStrings, profile: ProfileDto): TemplateResult {
    const brand = profile.brand_name;
    const speakerType = localizedSpeakerTypeLabel(profile, this.locale);
    const title = localizedModelName(profile, this.locale) ?? profile.name;
    const editCount = this.editCount;
    return html`
      <div class="heading-row">
        <div class="heading-text">
          <div class="breadcrumb">
            ${brand === null || speakerType === null
              ? nothing
              : html`<span>${brand}</span><span aria-hidden="true">/</span
                  ><span>${speakerType}</span>`}
            ${this.factoryData === undefined
              ? nothing
              : html`<span class="badge ${editCount === 0 ? "" : "edited"}"
                  >${editBadgeText(strings, editCount)}</span
                >`}
          </div>
          <h2 class="profile-title">${title}</h2>
          <profile-activation
            .profileId=${profile.id}
            .active=${this.activeProfile}
            ?hasDraft=${this.draft !== null}
            ?busy=${this.activating}
            .locale=${this.locale}
            @activate-profile=${(activateEvent: CustomEvent<{ id: number }>) =>
              this.activateProfile(activateEvent.detail.id)}
          ></profile-activation>
        </div>
        ${this.isPhoneLayout ? nothing : this.renderHeadingActions(strings, editCount)}
      </div>
    `;
  }

  private renderHeadingActions(
    strings: UiStrings,
    editCount: number,
  ): TemplateResult | typeof nothing {
    if (editCount === 0) {
      // A profile with no factory counterpart has nothing to compare
      // against, so it has no hint about a version of its own either.
      return this.factoryData === undefined
        ? nothing
        : html`<span class="start-hint">${strings.startEditingHint}</span>`;
    }
    return html`
      <div class="heading-actions">
        <button type="button" class="secondary" @click=${() => this.revertToFactory()}>
          ${strings.revertToFactory}
        </button>
        ${this.draft === null
          ? nothing
          : html`
              <button type="button" class="primary" @click=${() => this.saveDraftAsProfile()}>
                ${strings.saveAsMyProfile}
              </button>
            `}
      </div>
    `;
  }

  /** The phone puts the same actions in a bar above the tab bar. */
  private renderSaveBar(strings: UiStrings): TemplateResult | typeof nothing {
    const editCount = this.editCount;
    if (editCount === 0) {
      return nothing;
    }
    return html`
      <div class="save-bar">
        <span class="badge edited">${editBadgeText(strings, editCount)}</span>
        <button type="button" class="secondary" @click=${() => this.revertToFactory()}>
          ${strings.revertShort}
        </button>
        ${this.draft === null
          ? nothing
          : html`
              <button type="button" class="primary" @click=${() => this.saveDraftAsProfile()}>
                ${strings.saveShort}
              </button>
            `}
      </div>
    `;
  }

  /** The phone header replaces the wordmark and the profiles button
   * with the selected profile, which opens the sheet. */
  private renderPhoneProfileButton(strings: UiStrings): TemplateResult {
    const profile = this.selectedProfile;
    const title =
      profile === undefined
        ? strings.profilesButton
        : (localizedModelName(profile, this.locale) ?? profile.name);
    const caption =
      profile === undefined ? null : localizedSpeakerTypeLabel(profile, this.locale);
    return html`
      <button type="button" class="profiles-toggle phone" @click=${() => this.openProfilesDrawer()}>
        <span class="phone-profile-text">
          <span class="phone-profile-title">${title}</span>
          ${caption === null
            ? nothing
            : html`<span class="phone-profile-caption">${caption}</span>`}
        </span>
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
          <path
            d="M3 5 L7 9 L11 5"
            fill="none"
            stroke="currentColor"
            stroke-width="1.6"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>
    `;
  }

  /** The phone header has no room for the language control, so the
   * phone layout puts it in the profiles sheet instead. */
  private renderLocaleSwitcher(): TemplateResult {
    return html`
      <locale-switcher
        .locale=${this.locale}
        @locale-change=${(localeChangeEvent: CustomEvent<{ locale: Locale }>) =>
          this.changeLocale(localeChangeEvent.detail.locale)}
      ></locale-switcher>
    `;
  }

  /** Tablet and desktop show one page at a time, with all of its panels.
   * The grid areas in `app-root.styles.ts` place them per layout. */
  private renderWidePanels(strings: UiStrings): TemplateResult {
    if (this.page === "car") {
      return html`
        ${this.renderCarHeading(strings)}
        <div class="panels car">${this.renderSpeakerPanel()} ${this.renderCarCorrection(strings)}</div>
      `;
    }
    return html`
      ${this.renderCarLine(strings)}
      <div class="panels sound">
        ${this.renderAudioPanel()} ${this.renderEqPanel()} ${this.renderStylePanel()}
      </div>
    `;
  }

  private renderPageSwitch(strings: UiStrings): TemplateResult {
    const pages: ReadonlyArray<{ id: AppPage; label: string }> = [
      { id: "sound", label: strings.pageSound },
      { id: "car", label: strings.pageCar },
    ];
    return html`
      <nav class="page-switch">
        ${pages.map(
          (page) => html`
            <button
              type="button"
              aria-pressed=${this.page === page.id}
              @click=${() => this.selectPage(page.id)}
            >
              ${page.label}
            </button>
          `,
        )}
      </nav>
    `;
  }

  /** The selected profile's heading, or the prompt to pick one. */
  private renderCarHeading(strings: UiStrings): TemplateResult {
    const profile = this.selectedProfile;
    return profile === undefined ? renderNoSelection(strings) : this.renderHeadingRow(strings, profile);
  }

  /** The Sound page names the car profile that plays, and opens it. */
  private renderCarLine(strings: UiStrings): TemplateResult | typeof nothing {
    const activeId = this.activeProfile?.profile_id ?? null;
    const active = this.profiles.find((profile) => profile.id === activeId);
    if (active === undefined) {
      return nothing;
    }
    return html`
      <button type="button" class="car-line" @click=${() => this.openCar(active.id)}>
        <span class="car-line-label">${strings.pageCar}</span>
        <span class="car-line-name">${localizedProfileName(active, this.locale)}</span>
        <span aria-hidden="true">›</span>
      </button>
    `;
  }

  /** Shows a profile on the Car page, or the Car tab on the phone. */
  private openCar(id: number): void {
    this.selectProfile(id);
    this.page = "car";
    this.phoneTab = "car";
  }

  /** The phone shows one tab at a time. */
  private renderPhonePanels(strings: UiStrings): TemplateResult {
    return html`<div class="panels">${this.renderPhoneTabContent(strings)}</div>`;
  }

  private renderPhoneTabContent(strings: UiStrings): TemplateResult {
    if (this.phoneTab === "car") {
      return html`
        ${this.renderCarHeading(strings)} ${this.renderSpeakerPanel()}
        ${this.renderCarCorrection(strings)}
      `;
    }
    if (this.phoneTab === "audio") {
      return this.renderAudioPanel();
    }
    return html`${this.renderCarLine(strings)} ${this.renderEqPanel()} ${this.renderStylePanel()}`;
  }

  /** Opening the audio tab reads at once, so it never shows the last tab's
   * absence for a full poll interval. */
  private selectPhoneTab(tab: PhoneTab): void {
    this.phoneTab = tab;
    if (tab === "audio") {
      void this.refreshAudioState();
    }
    if (tab === "car") {
      this.showActiveCarWhenNoneSelected();
    }
  }

  private selectPage(page: AppPage): void {
    this.page = page;
    if (page === "car") {
      this.showActiveCarWhenNoneSelected();
    }
  }

  /** The Car page shows the active car profile until the person picks one. */
  private showActiveCarWhenNoneSelected(): void {
    const activeId = this.activeProfile?.profile_id ?? null;
    if (this.selectedId === null && activeId !== null) {
      this.selectedId = activeId;
    }
  }

  private renderTabBar(strings: UiStrings): TemplateResult {
    const tabs: ReadonlyArray<{ id: PhoneTab; label: string }> = [
      { id: "audio", label: strings.audioTitle },
      { id: "eq", label: strings.tabEq },
      { id: "car", label: strings.pageCar },
    ];
    return html`
      <nav class="tab-bar">
        ${tabs.map(
          (tab) => html`
            <button
              type="button"
              class="tab"
              aria-pressed=${this.phoneTab === tab.id}
              @click=${() => this.selectPhoneTab(tab.id)}
            >
              ${tab.label}
            </button>
          `,
        )}
      </nav>
    `;
  }

  /** The EQ that plays, as the one curve to edit. It does not depend on the
   * selected profile: the EQ plays on top of whichever car profile is active.
   * The car profile's own correction curve sits on the Car page. */
  private renderEqPanel(): TemplateResult {
    return html`
      <equalizer-editor
        class="area-eq"
        .equalizer=${this.equalizerLibrary.shown}
        .locale=${this.locale}
        .layout=${this.layout}
        @equalizer-gains=${(gainsEvent: CustomEvent<{ gains: number[] }>) =>
          this.equalizerLibrary.changeGains(gainsEvent.detail.gains)}
        @rename-equalizer=${(renameEvent: CustomEvent<{ name: string }>) =>
          this.equalizerLibrary.rename(renameEvent.detail.name)}
        @delete-equalizer=${(deleteEvent: CustomEvent<{ id: number }>) =>
          this.equalizerLibrary.remove(deleteEvent.detail.id)}
      ></equalizer-editor>
    `;
  }

  /** The car profile's own correction curve. It belongs to the car, so the
   * phone shows it on the Speakers tab. The EQ on top of it does the music. */
  private renderCarCorrection(strings: UiStrings): TemplateResult | typeof nothing {
    const profile = this.selectedProfile;
    if (profile === undefined) {
      return nothing;
    }
    return html`
      <eq-editor
        class="area-correction car-correction"
        .heading=${strings.carCorrectionTitle}
        .gains=${equalizerGains(this.shownData ?? profile.data)}
        .factoryGains=${this.factoryGains}
        .locale=${this.locale}
        .layout=${this.layout}
        @gain-change=${(gainChangeEvent: CustomEvent<{ band: number; value: number }>) =>
          this.changeGain(gainChangeEvent.detail.band, gainChangeEvent.detail.value)}
      ></eq-editor>
    `;
  }

  private renderSpeakerPanel(): TemplateResult {
    const profile = this.selectedProfile;
    if (profile === undefined) {
      return html`<div class="area-speakers"></div>`;
    }
    return html`
      <div class="area-speakers">
        <speaker-panel
          .speakers=${(this.shownData ?? profile.data).speakers}
          .locale=${this.locale}
          .layout=${this.layout}
          @speaker-change=${(
            speakerChangeEvent: CustomEvent<{
              channel: string;
              field: keyof Speaker;
              value: number | boolean;
            }>,
          ) =>
            this.changeSpeaker(
              speakerChangeEvent.detail.channel,
              speakerChangeEvent.detail.field,
              speakerChangeEvent.detail.value,
            )}
        ></speaker-panel>
      </div>
    `;
  }

  /** The ids this panel offers are the unit's own value sets, read once
   * at startup. The backend reads them from the Pioneer app's enums, so
   * the request needs no connected unit. A failed request leaves the panel
   * empty, and the app shows no guessed list. See dsp-presets.ts for why
   * there is no local fallback list any more. */
  private async loadDeviceOptions(): Promise<void> {
    try {
      const options = await this.api.readDeviceOptions();
      this.liveSimulationIds = options.live_simulations.map(
        (value) => value.name,
      ) as LiveSimulationId[];
      this.audioSourceNames = options.audio_sources.map((value) => value.name);
    } catch {
      // The backend is out of reach, so the panel stays empty until the
      // next page load. device-status.ts reports the link in the header.
    }
  }

  private renderAudioPanel(): TemplateResult {
    return html`
      <div class="area-audio">
        <audio-controls
          .locale=${this.locale}
          .state=${this.audioState}
          .sourceNames=${this.audioSourceNames}
          .busy=${this.audioBusy}
          .connected=${this.unitConnected}
          @volume-change=${(volumeChangeEvent: CustomEvent<{ volumeDb: number }>) =>
            this.changeVolume(volumeChangeEvent.detail.volumeDb)}
          @audio-source-change=${(sourceChangeEvent: CustomEvent<{ name: string }>) =>
            this.changeAudioSource(sourceChangeEvent.detail.name)}
        ></audio-controls>
      </div>
    `;
  }

  /** The audio panel follows the link. It reads as soon as the unit comes up
   * and then on a timer, and it forgets what it read when the unit goes
   * away: a volume shown for a unit that is not there is a stale number
   * nobody should act on. */
  private onLinkState(linkState: LinkState): void {
    const connected = linkState === "connected";
    if (connected === this.unitConnected) {
      return;
    }
    this.unitConnected = connected;
    // The backend pushes the active profile as the link comes up, and a
    // dropped link leaves it waiting. Either way the status changed.
    void this.loadActiveProfile();
    if (connected) {
      void this.pollAudio();
    } else {
      this.stopAudioPolling();
      this.audioState = null;
    }
  }

  /** The timer reads only when someone can see the result. The phone shows
   * one tab at a time, and a read nobody looks at is USB traffic for
   * nothing. It also waits out a write in flight, and a hidden page. */
  private get audioPanelVisible(): boolean {
    const pageHidden = typeof document !== "undefined" && document.visibilityState === "hidden";
    return !pageHidden && (!this.isPhoneLayout || this.phoneTab === "audio");
  }

  private async pollAudio(): Promise<void> {
    if (this.audioPanelVisible && !this.audioBusy) {
      await this.refreshAudioState();
    }
    this.stopAudioPolling();
    if (this.unitConnected) {
      this.audioPollHandle = this.scheduleFunction(() => {
        void this.pollAudio();
      }, AUDIO_POLL_MS);
    }
  }

  private stopAudioPolling(): void {
    if (this.audioPollHandle !== undefined) {
      this.cancelFunction(this.audioPollHandle);
      this.audioPollHandle = undefined;
    }
  }

  /** Reads what the unit does with sound. The header poll leaves it out,
   * because this read opens a link and that poll does not. See the note
   * in `audio-controls.ts`. Failure leaves the last known state up rather
   * than clearing it: a stale reading beats no reading while the next poll
   * retries. */
  private async refreshAudioState(): Promise<void> {
    if (!this.unitConnected) {
      return;
    }
    try {
      const read = await this.api.readAudioState();
      // A write that began while this read was in flight has newer news.
      if (!this.audioBusy) {
        this.audioState = read;
      }
    } catch {
      // The unit is not reachable. Keep showing whatever was last read.
    }
  }

  private async changeVolume(volumeDb: number): Promise<void> {
    if (!this.unitConnected) {
      return;
    }
    this.audioBusy = true;
    try {
      this.audioState = await this.api.setVolume(volumeDb);
    } catch {
      // The unit is not reachable. The control reverts to the last
      // known state on its own next render.
    } finally {
      this.audioBusy = false;
    }
  }

  private async changeAudioSource(name: string): Promise<void> {
    if (!this.unitConnected) {
      return;
    }
    this.audioBusy = true;
    try {
      this.audioState = await this.api.setAudioSource(name);
    } catch {
      // Same as changeVolume: the unit is not reachable.
    } finally {
      this.audioBusy = false;
    }
  }

  private async changeLiveSimulation(id: LiveSimulationId): Promise<void> {
    this.liveSimulation = id;
    await this.sendToUnit(() => this.api.selectLiveSimulation(id));
  }

  private async sendToUnit(send: () => Promise<unknown>): Promise<void> {
    try {
      await send();
    } catch {
      // The unit is not reachable. The panel keeps the local choice, and
      // the header already says the unit is not connected.
    }
  }

  private renderStylePanel(): TemplateResult {
    return html`
      <dsp-panel
        class="area-style"
        .locale=${this.locale}
        .equalizers=${this.equalizerLibrary.equalizers}
        .activeEqualizerId=${this.activeProfile === null
          ? undefined
          : this.activeProfile.equalizer_id}
        .liveSimulationIds=${this.liveSimulationIds}
        .liveSimulation=${this.liveSimulation}
        @activate-equalizer=${(activateEvent: CustomEvent<{ id: number | null }>) =>
          this.equalizerLibrary.activate(activateEvent.detail.id)}
        @favorite-equalizer=${(favoriteEvent: CustomEvent<{ id: number; favorite: boolean }>) =>
          this.equalizerLibrary.setFavorite(favoriteEvent.detail.id, favoriteEvent.detail.favorite)}
        @live-simulation-change=${(
          liveSimulationChangeEvent: CustomEvent<{ id: LiveSimulationId }>,
        ) => this.changeLiveSimulation(liveSimulationChangeEvent.detail.id)}
      ></dsp-panel>
    `;
  }

  private changeLocale(locale: Locale): void {
    this.locale = locale;
    saveLocale(this.localeStorage, locale);
  }

  private openProfilesDrawer(): void {
    this.profilesDrawerOpen = true;
  }

  private closeProfilesDrawer(): void {
    this.profilesDrawerOpen = false;
  }

  private async loadProfiles(): Promise<void> {
    this.profiles = await this.api.listProfiles();
  }

  private selectProfile(id: number): void {
    if (id === this.selectedId) {
      this.closeProfilesDrawer();
      return;
    }
    if (this.draft !== null && !this.confirmDiscard(uiStrings(this.locale).discardDraftConfirm)) {
      return;
    }
    this.draft = null;
    this.selectedId = id;
    this.page = "car";
    this.phoneTab = "car";
    this.closeProfilesDrawer();
  }

  private async duplicateProfile(id: number): Promise<void> {
    const copy = await this.api.duplicateProfile(id);
    await this.loadProfiles();
    this.draft = null;
    this.selectedId = copy.id;
    this.closeProfilesDrawer();
  }

  /** Starts a profile of your own from nothing: a flat curve and neutral
   * speakers. A copy of a preset comes from "Save as my profile" or
   * Duplicate. Unsaved edits would be lost, so ask first. */
  private async createProfile(): Promise<void> {
    if (this.draft !== null && !this.confirmDiscard(uiStrings(this.locale).discardDraftConfirm)) {
      return;
    }
    const created = await this.api.createProfile({
      name: uiStrings(this.locale).newProfileName,
      data: blankTuningData(),
    });
    this.draft = null;
    await this.loadProfiles();
    this.selectedId = created.id;
    this.closeProfilesDrawer();
  }

  /** Keeps the tune the unit holds now as a profile of its own. A Pioneer
   * app may have tuned the unit, and a push replaces that tune. A unit that
   * does not answer leaves the list as it was. The header already says why. */
  private async saveUnitProfile(): Promise<void> {
    let saved: ProfileDto;
    try {
      saved = await this.api.saveUnitProfile(uiStrings(this.locale).unitTuneName);
    } catch {
      return;
    }
    this.draft = null;
    await this.loadProfiles();
    this.selectedId = saved.id;
    this.closeProfilesDrawer();
  }

  private async changeFavorite(ids: readonly number[], favorite: boolean): Promise<void> {
    const updated = await Promise.all(ids.map((id) => this.api.setFavorite(id, favorite)));
    const byId = new Map(updated.map((profile) => [profile.id, profile]));
    this.profiles = this.profiles.map((profile) => byId.get(profile.id) ?? profile);
  }

  /** Reads which profile the unit plays. A backend out of reach leaves the
   * last answer on screen, and the header already says why. */
  private async loadActiveProfile(): Promise<void> {
    try {
      this.activeProfile = await this.api.readActiveProfile();
    } catch {
      // Keep the last known status.
    }
  }

  /** Makes a profile the one the unit plays. The backend pushes it now when
   * the unit is connected, and on the next connect otherwise. */
  private async activateProfile(id: number): Promise<void> {
    this.activating = true;
    try {
      this.activeProfile = await this.api.activateProfile(id);
    } catch {
      // The backend is out of reach. The status stays as it was.
    } finally {
      this.activating = false;
    }
  }

  private async renameProfile(id: number, name: string): Promise<void> {
    const updated = await this.api.updateProfile(id, { name });
    this.profiles = this.profiles.map((profile) => (profile.id === id ? updated : profile));
  }

  private async deleteProfile(id: number): Promise<void> {
    if (this.unsavedEdit?.profileId === id) {
      this.unsavedEdit = null;
    }
    await this.api.deleteProfile(id);
    if (this.selectedId === id) {
      this.selectedId = null;
    }
    await this.loadProfiles();
    // The backend forgets a deleted active profile.
    await this.loadActiveProfile();
  }

  private async changeGain(band: number, gain: number): Promise<void> {
    const profile = this.selectedProfile;
    const shown = this.shownData;
    if (profile === undefined || shown === undefined) {
      return;
    }
    await this.applyEdit(profile, withEqualizerGain(shown, band, gain));
  }

  private async changeSpeaker(
    channel: string,
    field: keyof Speaker,
    value: number | boolean,
  ): Promise<void> {
    const profile = this.selectedProfile;
    const shown = this.shownData;
    if (profile === undefined || shown === undefined) {
      return;
    }
    await this.applyEdit(profile, withSpeakerField(shown, channel, field, value));
  }

  /** A custom profile saves every edit. A factory preset keeps its
   * edits in the draft until the user saves them as a new profile. */
  private async applyEdit(profile: ProfileDto, data: TuningDataDto): Promise<void> {
    if (profile.source === "factory") {
      this.draft = data;
      return;
    }
    this.unsavedEdit = { profileId: profile.id, data };
    await this.saveUnsavedEdits();
  }

  /** Sends custom-profile edits one save at a time, and always the newest.
   *
   * A drag fires an edit on every 0.5 dB step. Each one used to start its
   * own save, and each save put the backend's reply on screen when it came
   * back. An older reply could land after a newer edit, so the curve jumped
   * back while the pointer moved on. Now the screen shows the newest edit,
   * and one save runs at a time. The edits a save missed go in the next one.
   */
  private async saveUnsavedEdits(): Promise<void> {
    if (this.savingEdits) {
      return;
    }
    this.savingEdits = true;
    try {
      while (this.unsavedEdit !== null) {
        const edit = this.unsavedEdit;
        await this.saveProfileData(edit.profileId, edit.data);
        if (this.unsavedEdit === edit) {
          this.unsavedEdit = null;
        }
      }
    } catch {
      // The backend did not take the edit. The screen keeps it, and the
      // next edit tries the save again.
    } finally {
      this.savingEdits = false;
    }
  }

  private revertToFactory(): void {
    this.draft = null;
    const profile = this.selectedProfile;
    const factory = this.factoryData;
    if (profile === undefined || factory === undefined || profile.source === "factory") {
      return;
    }
    this.unsavedEdit = { profileId: profile.id, data: factory };
    void this.saveUnsavedEdits();
  }

  /** Copies the factory preset, writes the draft into the copy, then
   * selects it. */
  private async saveDraftAsProfile(): Promise<void> {
    const profile = this.selectedProfile;
    const draft = this.draft;
    if (profile === undefined || draft === null) {
      return;
    }
    const copy = await this.api.duplicateProfile(profile.id);
    await this.api.updateProfile(copy.id, { data: draft });
    this.draft = null;
    await this.loadProfiles();
    this.selectedId = copy.id;
  }

  private async saveProfileData(id: number, data: ProfileDto["data"]): Promise<void> {
    const updated = await this.api.updateProfile(id, { data });
    this.profiles = this.profiles.map((profile) => (profile.id === id ? updated : profile));
    // An edit of the active profile leaves the unit on the older version.
    if (id === this.activeProfile?.profile_id) {
      await this.loadActiveProfile();
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "app-root": AppRoot;
  }
}
