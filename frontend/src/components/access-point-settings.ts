import { html, LitElement, nothing, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { WifiApi } from "../api/client.ts";
import type { AccessPointDto } from "../dto/profile.dto.ts";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import { accessPointSettingsStyles } from "./access-point-settings.styles.ts";
import { isValidNetwork, wifiErrorMessage } from "./wifi-settings.ts";

/** WPA2's rules, with no open network: the access point always has a key. */
export function isValidAccessPointKey(key: string): boolean {
  return key !== "" && isValidNetwork("-", key);
}

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
  @state() private message = "";
  @state() private isBusy = false;
  @state() private key = "";
  @state() private repeatedKey = "";

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
        ${this.renderForm(strings)}
        ${this.message ? html`<p class="message" role="status">${this.message}</p>` : nothing}
      </section>
    `;
  }

  private renderForm(strings: UiStrings): TemplateResult {
    const canSave = !this.isBusy && isValidAccessPointKey(this.key) && this.key === this.repeatedKey;
    return html`
      <form @submit=${(submitEvent: SubmitEvent) => this.save(submitEvent, strings)}>
        <label>
          ${strings.accessPointKeyLabel}
          <input name="key" type="password" autocomplete="new-password" .value=${this.key}
            @input=${(inputEvent: InputEvent) => (this.key = (inputEvent.target as HTMLInputElement).value)} />
          <span class="hint">${strings.accessPointKeyHint}</span>
        </label>
        <label>
          ${strings.accessPointRepeatLabel}
          <input name="repeated-key" type="password" autocomplete="new-password" .value=${this.repeatedKey}
            @input=${(inputEvent: InputEvent) => (this.repeatedKey = (inputEvent.target as HTMLInputElement).value)} />
        </label>
        <button type="submit" class="save" ?disabled=${!canSave}>${strings.accessPointSave}</button>
      </form>
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

  private async save(submitEvent: SubmitEvent, strings: UiStrings): Promise<void> {
    submitEvent.preventDefault();
    if (this.api === undefined) {
      return;
    }
    this.isBusy = true;
    this.message = "";
    try {
      this.accessPoint = await this.api.setAccessPointKey(this.key);
      this.key = "";
      this.repeatedKey = "";
      this.message = strings.accessPointSaved.replace("{ssid}", this.accessPoint.ssid);
    } catch (caughtError) {
      this.message = wifiErrorMessage(strings, caughtError);
    } finally {
      this.isBusy = false;
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "access-point-settings": AccessPointSettings;
  }
}
