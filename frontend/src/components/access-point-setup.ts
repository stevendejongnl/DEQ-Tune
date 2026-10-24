import { html, LitElement } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { WifiApi } from "../api/client.ts";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings } from "../i18n/ui-strings.ts";
import "./access-point-key-form.ts";
import { accessPointSetupStyles } from "./access-point-setup.styles.ts";

/**
 * The first-run step that asks for an own access point key while the Pi
 * still uses the public default key.
 *
 * Set `api`, `locale` and `ssid`. It fires `access-point-setup-skipped` on
 * "Later" and `access-point-setup-closed` on "Done" after a saved key. The
 * key form inside it fires `access-point-key-saved`. app-root decides when
 * it shows. It depends on a `WifiApi`.
 */
@customElement("access-point-setup")
export class AccessPointSetup extends LitElement {
  static override styles = accessPointSetupStyles;

  @property({ attribute: false }) api: Pick<WifiApi, "setAccessPointKey"> | undefined;
  @property({ type: String }) locale: Locale = "en";
  @property({ type: String }) ssid = "";

  @state() private saved = false;

  override render() {
    const strings = uiStrings(this.locale);
    return html`
      <div class="card" role="dialog" aria-modal="true" aria-labelledby="title">
        <h2 id="title">${strings.accessPointSetupTitle}</h2>
        <p>${strings.accessPointSetupIntro.replace("{ssid}", this.ssid)}</p>
        <access-point-key-form
          .api=${this.api}
          .locale=${this.locale}
          @access-point-key-saved=${() => (this.saved = true)}
        ></access-point-key-form>
        <div class="footer">
          ${this.saved
            ? html`<button type="button" class="done" @click=${() => this.fire("access-point-setup-closed")}>
                ${strings.accessPointSetupDone}
              </button>`
            : html`<button type="button" class="later" @click=${() => this.fire("access-point-setup-skipped")}>
                ${strings.accessPointSetupLater}
              </button>`}
        </div>
      </div>
    `;
  }

  private fire(name: string): void {
    this.dispatchEvent(new CustomEvent(name));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "access-point-setup": AccessPointSetup;
  }
}
