import { html, LitElement, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { WifiApi } from "../api/client.ts";
import type { AccessPointDto } from "../dto/profile.dto.ts";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings } from "../i18n/ui-strings.ts";
import "./access-point-key-form.ts";
import { accessPointSettingsStyles } from "./access-point-settings.styles.ts";

/**
 * Lets a person replace the access point's public default key.
 *
 * It renders the access point's name, whether it still uses the default
 * key, and a form for a new one, as part of the settings page's Wi-Fi
 * section. A Pi without an access point renders nothing. It depends on a
 * `WifiApi`.
 *
 * The new key applies at the Pi's next start. A restart of the access point
 * now would drop the phone that sent the key.
 */
@customElement("access-point-settings")
export class AccessPointSettings extends LitElement {
  static override styles = accessPointSettingsStyles;

  @property({ attribute: false }) api: WifiApi | undefined;
  @property({ type: String }) locale: Locale = "en";

  @state() private accessPoint: AccessPointDto | null = null;

  override connectedCallback(): void {
    super.connectedCallback();
    void this.load();
  }

  override render() {
    if (this.accessPoint === null) {
      return nothing;
    }
    const strings = uiStrings(this.locale);
    return html`
      <section>
        <h3>${strings.accessPointTitle}</h3>
        <p class="intro">${strings.accessPointIntro.replace("{ssid}", this.accessPoint.ssid)}</p>
        ${this.accessPoint.uses_default_key
          ? html`<p class="warning">${strings.accessPointDefaultKey}</p>`
          : html`<p class="intro">${strings.accessPointOwnKey}</p>`}
        <access-point-key-form
          .api=${this.api}
          .locale=${this.locale}
          @access-point-key-saved=${(savedEvent: CustomEvent<{ accessPoint: AccessPointDto }>) =>
            (this.accessPoint = savedEvent.detail.accessPoint)}
        ></access-point-key-form>
      </section>
    `;
  }

  /** Reads the access point fresh. Any failure hides the section: the Wi-Fi
   * section above already reports a Pi that cannot manage Wi-Fi. */
  async load(): Promise<void> {
    if (this.api === undefined) {
      return;
    }
    try {
      this.accessPoint = await this.api.readAccessPoint();
    } catch {
      this.accessPoint = null;
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "access-point-settings": AccessPointSettings;
  }
}
