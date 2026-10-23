import { html, LitElement, type TemplateResult } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { BridgeSystemApi, WifiApi } from "../api/client.ts";
import { BUILD_ID } from "../build-id.ts";
import type { UpdatesDto } from "../dto/profile.dto.ts";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import "./locale-switcher.ts";
import { settingsPageStyles } from "./settings-page.styles.ts";
import "./system-panel.ts";
import "./update-settings.ts";
import type { UpdateRequestState } from "./updates-controller.ts";
import "./wifi-settings.ts";

export type SettingsSection = "updates" | "wifi" | "system" | "language";

export const SETTINGS_SECTIONS: readonly SettingsSection[] = ["updates", "wifi", "system", "language"];

function sectionTitle(strings: UiStrings, section: SettingsSection): string {
  return {
    updates: strings.settingsSectionUpdates,
    wifi: strings.settingsSectionWifi,
    system: strings.settingsSectionSystem,
    language: strings.settingsSectionLanguage,
  }[section];
}

/**
 * The settings page, laid out as Fluidd lays out its own: a list of
 * sections, and one card for the chosen section.
 *
 * It holds the Pi's updates, its Wi-Fi networks, its system statistics,
 * and the app's language. app-root opens it from the header's gear button,
 * and opens the System section from the status pill. It fires
 * `section-change` ({ section }) and passes on `locale-change`. The
 * sections do their own reading, except Updates, whose state app-root keeps
 * for the notification dock too.
 */
@customElement("settings-page")
export class SettingsPage extends LitElement {
  static override styles = settingsPageStyles;

  @property({ attribute: false }) api: (WifiApi & BridgeSystemApi) | undefined;
  @property({ type: String }) locale: Locale = "en";
  @property({ type: String }) section: SettingsSection = "updates";
  @property({ attribute: false }) updates: UpdatesDto | null = null;
  @property({ type: String }) requestState: UpdateRequestState = "idle";
  @property({ type: String }) pageBuild = BUILD_ID;

  override render() {
    const strings = uiStrings(this.locale);
    return html`
      <nav class="sections" aria-label=${strings.settingsTitle}>
        ${SETTINGS_SECTIONS.map(
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
  private renderSection(strings: UiStrings): TemplateResult {
    switch (this.section) {
      case "updates":
        return html`<update-settings .updates=${this.updates} .requestState=${this.requestState}
          .locale=${this.locale}></update-settings>`;
      case "wifi":
        return html`<wifi-settings .api=${this.api} .locale=${this.locale}></wifi-settings>`;
      case "system":
        return html`<system-panel .api=${this.api} .locale=${this.locale} .pageBuild=${this.pageBuild}></system-panel>`;
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
    `;
  }

  private selectSection(section: SettingsSection): void {
    this.dispatchEvent(new CustomEvent("section-change", { detail: { section } }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "settings-page": SettingsPage;
  }
}
