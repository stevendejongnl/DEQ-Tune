import { html, LitElement, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { WifiApi } from "../api/client.ts";
import type { AccessPointDto } from "../dto/profile.dto.ts";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import { accessPointKeyFormStyles } from "./access-point-key-form.styles.ts";
import { busyStyles } from "./busy.styles.ts";
import { isValidNetwork, wifiErrorMessage } from "./wifi-settings.ts";

/** WPA2's rules, with no open network: the access point always has a key. */
export function isValidAccessPointKey(key: string): boolean {
  return key !== "" && isValidNetwork("-", key);
}

/**
 * Asks twice for a new access point key and sends it to the Pi.
 *
 * Set `api` and `locale`. After the Pi takes the key, it says so and fires
 * `access-point-key-saved` ({ accessPoint }). That event bubbles out of
 * every shadow root, so app-root hears it too. It depends on a `WifiApi`.
 */
@customElement("access-point-key-form")
export class AccessPointKeyForm extends LitElement {
  static override styles = [accessPointKeyFormStyles, busyStyles];

  @property({ attribute: false }) api: Pick<WifiApi, "setAccessPointKey"> | undefined;
  @property({ type: String }) locale: Locale = "en";

  @state() private message = "";
  @state() private isBusy = false;
  @state() private key = "";
  @state() private repeatedKey = "";

  override render() {
    const strings = uiStrings(this.locale);
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
        <button type="submit" class="save" ?disabled=${!canSave} aria-busy=${this.isBusy}>${strings.accessPointSave}</button>
      </form>
      ${this.message ? html`<p class="message" role="status">${this.message}</p>` : nothing}
    `;
  }

  private async save(submitEvent: SubmitEvent, strings: UiStrings): Promise<void> {
    submitEvent.preventDefault();
    if (this.api === undefined) {
      return;
    }
    this.isBusy = true;
    this.message = "";
    try {
      const accessPoint = await this.api.setAccessPointKey(this.key);
      this.key = "";
      this.repeatedKey = "";
      this.message = strings.accessPointSaved.replace("{ssid}", accessPoint.ssid);
      this.announceSaved(accessPoint);
    } catch (caughtError) {
      this.message = wifiErrorMessage(strings, caughtError);
    } finally {
      this.isBusy = false;
    }
  }

  private announceSaved(accessPoint: AccessPointDto): void {
    this.dispatchEvent(
      new CustomEvent("access-point-key-saved", { detail: { accessPoint }, bubbles: true, composed: true }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "access-point-key-form": AccessPointKeyForm;
  }
}
