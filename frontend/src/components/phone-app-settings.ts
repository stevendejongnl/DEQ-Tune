import { html, LitElement, nothing, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { PhoneAppApi, PhoneAppState, PhoneConnectionMode } from "../api/phone-app.ts";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import { phoneAppSettingsStyles } from "./phone-app-settings.styles.ts";

const MODES: readonly PhoneConnectionMode[] = ["AUTOMATIC", "BLUETOOTH", "ACCESS_POINT"];

function modeLabel(strings: UiStrings, mode: PhoneConnectionMode): string {
  return { AUTOMATIC: strings.phoneModeAutomatic, BLUETOOTH: strings.phoneModeBluetooth, ACCESS_POINT: strings.phoneModeAccessPoint }[mode];
}

function modeHint(strings: UiStrings, mode: PhoneConnectionMode): string {
  return { AUTOMATIC: strings.phoneModeAutomaticHint, BLUETOOTH: strings.phoneModeBluetoothHint, ACCESS_POINT: strings.phoneModeAccessPointHint }[mode];
}

/** Says in words how the phone reaches the Pi now. */
export function connectionText(strings: UiStrings, state: PhoneAppState): string {
  switch (state.connection) {
    case "wifi":
      return strings.phoneConnectedWifi.replace("{address}", state.pi_address ?? "");
    case "bluetooth":
      // In Bluetooth only, the app does not look on Wi-Fi, so it cannot say where the Pi is.
      return state.mode === "BLUETOOTH" ? strings.phoneConnectedBluetoothOnly : strings.phoneConnectedBluetooth;
    case "access_point":
      return strings.phoneConnectedAccessPoint;
    case "searching":
      return strings.phoneSearching;
  }
}

/**
 * The car app's own settings, inside the web app: how the phone reaches the
 * Pi, the access point details, and the permissions.
 *
 * It renders as the settings page's Phone app section, which the page shows
 * only inside the car app. It depends on a `PhoneAppApi`, which a test
 * replaces. It reads the state again on each change that the car app
 * reports, such as the end of a search for the Pi.
 */
@customElement("phone-app-settings")
export class PhoneAppSettings extends LitElement {
  static override styles = phoneAppSettingsStyles;

  @property({ attribute: false }) api: PhoneAppApi | null = null;
  @property({ type: String }) locale: Locale = "en";

  @state() private phone: PhoneAppState | null = null;
  @state() private ssid = "";
  @state() private password = "";
  @state() private url = "";
  @state() private message = "";

  private stopListening: (() => void) | null = null;

  override connectedCallback(): void {
    super.connectedCallback();
    this.stopListening = this.api?.onChange(() => this.read()) ?? null;
    this.read();
    this.resetAccessPointFields();
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    this.stopListening?.();
    this.stopListening = null;
  }

  override render() {
    if (this.phone === null) {
      return nothing;
    }
    const strings = uiStrings(this.locale);
    return html`
      <div class="status">
        <span role="status">${connectionText(strings, this.phone)}</span>
        <button type="button" class="search" ?disabled=${this.phone.connection === "searching"}
          @click=${() => this.api?.searchAgain()}>
          ${strings.phoneSearchAgain}
        </button>
      </div>
      ${this.phone.missing_permissions ? this.renderPermissions(strings) : nothing}
      ${this.renderModes(strings, this.phone)}
      ${this.phone.mode === "ACCESS_POINT" ? this.renderAccessPoint(strings, this.phone) : nothing}
      ${this.message ? html`<p class="message">${this.message}</p>` : nothing}
      <div class="footer">
        <span class="hint">${strings.phoneAppVersion.replace("{version}", this.phone.app_version)}</span>
      </div>
    `;
  }

  private renderPermissions(strings: UiStrings): TemplateResult {
    return html`
      <div class="warning">
        <span>${strings.phonePermissionsMissing}</span>
        <button type="button" class="allow" @click=${() => this.api?.askPermissions()}>${strings.phoneAllow}</button>
      </div>
    `;
  }

  private renderModes(strings: UiStrings, phone: PhoneAppState): TemplateResult {
    return html`
      <fieldset class="modes">
        <legend>${strings.phoneModeTitle}</legend>
        ${MODES.map(
          (mode) => html`
            <label class="mode">
              <input type="radio" name="mode" .value=${mode} .checked=${phone.mode === mode}
                @change=${() => this.saveMode(mode)} />
              <span>
                <span class="mode-label">${modeLabel(strings, mode)}</span>
                <span class="hint">${modeHint(strings, mode)}</span>
              </span>
            </label>
          `,
        )}
      </fieldset>
    `;
  }

  private renderAccessPoint(strings: UiStrings, phone: PhoneAppState): TemplateResult {
    return html`
      <form @submit=${(submitEvent: SubmitEvent) => this.saveAccessPoint(submitEvent, strings)}>
        <label>
          ${strings.wifiSsidLabel}
          <input name="ssid" autocomplete="off" autocapitalize="off" spellcheck="false" .value=${this.ssid}
            @input=${(inputEvent: InputEvent) => (this.ssid = (inputEvent.target as HTMLInputElement).value)} />
        </label>
        <label>
          ${strings.wifiPasswordLabel}
          <input name="password" type="password" autocomplete="off"
            placeholder=${phone.has_access_point_password ? strings.phonePasswordSaved : ""}
            .value=${this.password}
            @input=${(inputEvent: InputEvent) => (this.password = (inputEvent.target as HTMLInputElement).value)} />
        </label>
        <label>
          ${strings.phoneAccessPointUrl}
          <input name="url" autocomplete="off" autocapitalize="off" spellcheck="false" inputmode="url" .value=${this.url}
            @input=${(inputEvent: InputEvent) => (this.url = (inputEvent.target as HTMLInputElement).value)} />
        </label>
        <button type="submit" class="save" ?disabled=${this.ssid.trim() === "" || this.url.trim() === ""}>
          ${strings.wifiSave}
        </button>
      </form>
    `;
  }

  private read(): void {
    this.phone = this.api?.read() ?? null;
  }

  private resetAccessPointFields(): void {
    this.ssid = this.phone?.access_point_ssid ?? "";
    this.url = this.phone?.access_point_url ?? "";
    this.password = "";
  }

  private saveMode(mode: PhoneConnectionMode): void {
    if (this.phone === null) {
      return;
    }
    this.api?.save({
      mode,
      access_point_url: this.phone.access_point_url,
      access_point_ssid: this.phone.access_point_ssid,
      access_point_password: null,
    });
    this.message = "";
    this.read();
  }

  private saveAccessPoint(submitEvent: SubmitEvent, strings: UiStrings): void {
    submitEvent.preventDefault();
    this.api?.save({
      mode: "ACCESS_POINT",
      access_point_url: this.url.trim(),
      access_point_ssid: this.ssid.trim(),
      access_point_password: this.password === "" ? null : this.password,
    });
    this.read();
    this.resetAccessPointFields();
    this.message = strings.phoneSaved;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "phone-app-settings": PhoneAppSettings;
  }
}
