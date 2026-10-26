import { html, LitElement, nothing, type PropertyValues, type TemplateResult } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { BluetoothApi, BridgeSystemApi, LibraryApi, WifiApi } from "../api/client.ts";
import { CommunityLibraryClient, type CommunityLibraryApi } from "../api/community-library.ts";
import { phoneAppApi, type PhoneAppApi } from "../api/phone-app.ts";
import { BUILD_ID } from "../build-id.ts";
import type { UpdatesDto } from "../dto/profile.dto.ts";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import { downloadFile, type SaveFile } from "./library-backup.ts";
import "./community-library.ts";
import "./locale-switcher.ts";
import "./phone-app-settings.ts";
import { settingsPageStyles } from "./settings-page.styles.ts";
import "./system-panel.ts";
import "./update-settings.ts";
import type { UpdateRequestState } from "./updates-controller.ts";
import "./access-point-settings.ts";
import "./wifi-settings.ts";
import "./bluetooth-settings.ts";
import "./display-settings.ts";

/** Where people translate the app, and the guide for it. */
export const WEBLATE_PROJECT_URL = "https://hosted.weblate.org/projects/deq-tune/";
export const TRANSLATING_GUIDE_URL = "https://github.com/stevendejongnl/deq-tune/blob/main/TRANSLATING.md";

export type SettingsSection =
  | "phone"
  | "updates"
  | "wifi"
  | "bluetooth"
  | "backup"
  | "community"
  | "system"
  | "display"
  | "language";

export const SETTINGS_SECTIONS: readonly SettingsSection[] = [
  "phone",
  "updates",
  "wifi",
  "bluetooth",
  "backup",
  "community",
  "system",
  "display",
  "language",
];

/** The sections to list. Phone app exists only inside the car app. */
export function visibleSections(hasPhoneApp: boolean): SettingsSection[] {
  return SETTINGS_SECTIONS.filter((section) => section !== "phone" || hasPhoneApp);
}

function sectionTitle(strings: UiStrings, section: SettingsSection): string {
  return {
    phone: strings.settingsSectionPhone,
    updates: strings.settingsSectionUpdates,
    wifi: strings.settingsSectionWifi,
    bluetooth: strings.settingsSectionBluetooth,
    backup: strings.settingsSectionBackup,
    community: strings.settingsSectionCommunity,
    system: strings.settingsSectionSystem,
    display: strings.settingsSectionDisplay,
    language: strings.settingsSectionLanguage,
  }[section];
}

/**
 * The settings page, laid out as Fluidd lays out its own: a list of
 * sections, and one card for the chosen section.
 *
 * It holds the car app's own settings (inside the car app only), the Pi's
 * updates, its Wi-Fi networks, its Bluetooth pairing, the library backup, the community library,
 * its system statistics, and the app's language. app-root opens it from the header's gear button,
 * and opens the System section from the status pill. It fires
 * `section-change` ({ section }) and passes on `locale-change`. The
 * sections do their own reading, except Updates, whose state app-root keeps
 * for the notification dock too.
 */
@customElement("settings-page")
export class SettingsPage extends LitElement {
  static override styles = settingsPageStyles;

  @property({ attribute: false }) api: (WifiApi & BluetoothApi & BridgeSystemApi & LibraryApi) | undefined;
  @property({ type: String }) locale: Locale = "en";
  @property({ type: String }) section: SettingsSection = "updates";
  @property({ attribute: false }) updates: UpdatesDto | null = null;
  @property({ type: String }) requestState: UpdateRequestState = "idle";
  @property({ type: String }) pageBuild = BUILD_ID;
  /** The connected unit's firmware version, for the System section. */
  @property({ type: String }) firmwareVersion: string | null = null;
  /** The car app's settings, or null in a browser. */
  @property({ attribute: false }) phoneApp: PhoneAppApi | null = phoneAppApi();
  @property({ attribute: false }) community: CommunityLibraryApi = new CommunityLibraryClient();

  /** A tap within this time after the section list scrolled sideways
   * ends that swipe, so it does not open a section. */
  static readonly TAP_AFTER_SCROLL_MS = 150;

  /** The clock, which a test replaces. */
  @property({ attribute: false }) now: () => number = () => performance.now();

  private lastNavScrollAt = Number.NEGATIVE_INFINITY;

  /** On a phone the list scrolls sideways. The chosen section scrolls into view. */
  protected override updated(changed: PropertyValues): void {
    if (changed.has("section")) {
      const chosen = this.shadowRoot?.querySelector<HTMLElement>('.sections button[aria-pressed="true"]');
      if (typeof chosen?.scrollIntoView === "function") {
        chosen.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
      }
    }
  }

  override render() {
    const strings = uiStrings(this.locale);
    return html`
      <nav class="sections" aria-label=${strings.settingsTitle}
        @scroll=${() => (this.lastNavScrollAt = this.now())}>
        ${visibleSections(this.phoneApp !== null).map(
          (section) => html`
            <button type="button" aria-pressed=${this.section === section}
              @click=${() => this.selectSection(section)}>
              ${sectionTitle(strings, section)}
            </button>
          `,
        )}
      </nav>
      <section class="card">
        <h2>${sectionTitle(strings, this.section)}</h2>
        ${this.renderSection(strings)}
      </section>
    `;
  }

  /** Picks the one section to show. */
  /** Inside the car app, Android's save dialog. A WebView ignores a download. */
  private libraryFileSaver(): SaveFile {
    const phoneApp = this.phoneApp;
    return phoneApp === null ? downloadFile : (fileName, text) => phoneApp.saveFile(fileName, text);
  }

  private renderSection(strings: UiStrings): TemplateResult {
    switch (this.section) {
      case "phone":
        return html`<phone-app-settings .api=${this.phoneApp} .locale=${this.locale}></phone-app-settings>`;
      case "updates":
        return html`<update-settings .updates=${this.updates} .requestState=${this.requestState}
          .locale=${this.locale}></update-settings>`;
      case "wifi":
        return html`
          <wifi-settings .api=${this.api} .locale=${this.locale}></wifi-settings>
          <access-point-settings .api=${this.api} .locale=${this.locale}></access-point-settings>
        `;
      case "bluetooth":
        return html`<bluetooth-settings .api=${this.api} .locale=${this.locale}></bluetooth-settings>`;
      case "backup":
        return html`<library-backup .api=${this.api} .locale=${this.locale}
          .saveFile=${this.libraryFileSaver()}></library-backup>`;
      case "community":
        return html`<community-library .api=${this.api} .community=${this.community}
          .locale=${this.locale}></community-library>`;
      case "system":
        return html`<system-panel .api=${this.api} .locale=${this.locale} .pageBuild=${this.pageBuild}
          .firmwareVersion=${this.firmwareVersion}></system-panel>`;
      case "display":
        return html`<display-settings .locale=${this.locale}></display-settings>`;
      case "language":
        return this.renderLanguage(strings);
    }
  }

  private renderLanguage(strings: UiStrings): TemplateResult {
    return html`
      <div class="row">
        <span class="hint">${strings.settingsLanguageHint}</span>
        <locale-switcher .locale=${this.locale}
          @locale-change=${(localeEvent: CustomEvent<{ locale: Locale }>) =>
            this.dispatchEvent(new CustomEvent("locale-change", { detail: localeEvent.detail, bubbles: true, composed: true }))}
        ></locale-switcher>
      </div>
      ${this.phoneApp === null ? nothing : html`<p class="hint android-language">${strings.settingsLanguageAndroid}</p>`}
      <section class="translations">
        <h3>${strings.settingsTranslationsTitle}</h3>
        <p class="hint">${strings.settingsTranslationsText}</p>
        <ul class="links">
          <li><a href=${WEBLATE_PROJECT_URL} target="_blank" rel="noopener">${strings.settingsTranslateLink}</a></li>
          <li><a href=${TRANSLATING_GUIDE_URL} target="_blank" rel="noopener">${strings.settingsTranslatingGuideLink}</a></li>
        </ul>
      </section>
    `;
  }

  private selectSection(section: SettingsSection): void {
    if (this.now() - this.lastNavScrollAt < SettingsPage.TAP_AFTER_SCROLL_MS) {
      return;
    }
    this.dispatchEvent(new CustomEvent("section-change", { detail: { section } }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "settings-page": SettingsPage;
  }
}
