import { html, LitElement, nothing, type TemplateResult } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import { notificationDockStyles } from "./notification-dock.styles.ts";

/**
 * The bottom-left corner where the app says something on its own: what is
 * new after an update, that a new version waits for the Update button, and
 * that the Pi's network still uses the public default key.
 *
 * Nothing here blocks the page. The dock lets clicks through, and only the
 * cards' own controls take them. app-root places it once and decides what
 * it shows. Presentational: it fires `whats-new-dismissed` ({ version }),
 * `update-requested`, `update-postponed` ({ version }) and
 * `access-point-key-requested`.
 */
@customElement("notification-dock")
export class NotificationDock extends LitElement {
  static override styles = notificationDockStyles;

  @property({ type: String }) locale: Locale = "en";
  /** The release to announce, or null for no "what's new" card. */
  @property({ attribute: false }) whatsNewVersion: string | null = null;
  @property({ type: String }) highlight = "";
  @property({ type: String }) releaseUrl = "";
  /** A release that waits for the Update button, or null for no such card. */
  @property({ attribute: false }) availableVersion: string | null = null;
  /** True while the access point uses the default key after a skipped setup. */
  @property({ type: Boolean }) accessPointNotice = false;

  override render() {
    const strings = uiStrings(this.locale);
    return html`
      ${this.whatsNewVersion === null ? nothing : this.renderWhatsNew(strings, this.whatsNewVersion)}
      ${this.availableVersion === null ? nothing : this.renderAvailable(strings, this.availableVersion)}
      ${this.accessPointNotice ? this.renderAccessPointNotice(strings) : nothing}
    `;
  }

  private renderWhatsNew(strings: UiStrings, version: string): TemplateResult {
    return html`
      <article class="card whats-new" role="status">
        <div class="hero">
          <span class="badge">v${version}</span>
          <p class="headline">${strings.whatsNewTitle.replace("{version}", version)}</p>
          ${this.highlight ? html`<p class="highlight">${this.highlight}</p>` : nothing}
        </div>
        <div class="footer">
          ${this.releaseUrl
            ? html`<a href=${this.releaseUrl} target="_blank" rel="noopener">${strings.updatesChangelog} →</a>`
            : html`<span></span>`}
          <button type="button" class="primary"
            @click=${() => this.fire("whats-new-dismissed", { version })}>
            ${strings.whatsNewDismiss}
          </button>
        </div>
      </article>
    `;
  }

  private renderAvailable(strings: UiStrings, version: string): TemplateResult {
    return html`
      <article class="card available" role="status">
        <p class="headline">${strings.updateAvailableTitle.replace("{version}", version)}</p>
        <div class="footer">
          <button type="button" class="later" @click=${() => this.fire("update-postponed", { version })}>
            ${strings.updateAvailableLater}
          </button>
          <button type="button" class="primary" @click=${() => this.fire("update-requested", {})}>
            ${strings.updateAvailableInstall}
          </button>
        </div>
      </article>
    `;
  }

  /** Stays up until the key changes: it has no dismiss button. */
  private renderAccessPointNotice(strings: UiStrings): TemplateResult {
    return html`
      <article class="card access-point" role="status">
        <p class="headline">${strings.accessPointNoticeTitle}</p>
        <div class="footer">
          <span></span>
          <button type="button" class="primary" @click=${() => this.fire("access-point-key-requested", {})}>
            ${strings.accessPointNoticeAction}
          </button>
        </div>
      </article>
    `;
  }

  private fire(name: string, detail: object): void {
    this.dispatchEvent(new CustomEvent(name, { detail }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "notification-dock": NotificationDock;
  }
}
