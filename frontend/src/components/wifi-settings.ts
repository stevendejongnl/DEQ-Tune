import { html, LitElement, nothing, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { ApiError, type WifiApi } from "../api/client.ts";
import type { SavedWifiNetworkDto, WifiDto } from "../dto/profile.dto.ts";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import { wifiSettingsStyles } from "./wifi-settings.styles.ts";

const MINIMUM_PASSWORD_LENGTH = 8;
const MAXIMUM_PASSWORD_LENGTH = 63;
const HEX_KEY_PATTERN = /^[0-9a-fA-F]{64}$/;
const MAXIMUM_SSID_BYTES = 32;

/** The same rules as the backend's `WifiNetworkWrite`. The check here only
 * saves a round trip. The backend and the Pi's helper check again. */
export function isValidNetwork(ssid: string, password: string): boolean {
  const ssidBytes = new TextEncoder().encode(ssid).length;
  if (ssidBytes < 1 || ssidBytes > MAXIMUM_SSID_BYTES) {
    return false;
  }
  if (password === "" || HEX_KEY_PATTERN.test(password)) {
    return true;
  }
  return (
    password.length >= MINIMUM_PASSWORD_LENGTH &&
    password.length <= MAXIMUM_PASSWORD_LENGTH &&
    /^[\x20-\x7e]*$/.test(password)
  );
}

/** Turns a failed request into words for the person. */
export function wifiErrorMessage(strings: UiStrings, caughtError: unknown): string {
  if (caughtError instanceof ApiError) {
    if (caughtError.status === 503) {
      return strings.wifiUnavailable;
    }
    if (caughtError.status === 409) {
      return strings.wifiRefused;
    }
    if (caughtError.status === 422) {
      return strings.wifiInvalid;
    }
  }
  return strings.wifiFailed;
}

/**
 * Lets a person manage the Wi-Fi networks that the Pi joins, with no
 * terminal.
 *
 * It renders the saved networks and a form to add one, as a section of the
 * settings page. It reads the networks each time it comes onto the page,
 * because the Pi can join or leave one meanwhile. It depends on a
 * `WifiApi`, and on a confirm function that a test can answer.
 *
 * A save joins nothing at once. The Pi joins a saved network on its own,
 * and "Join now" asks it to try at once.
 */
@customElement("wifi-settings")
export class WifiSettings extends LitElement {
  static override styles = wifiSettingsStyles;

  @property({ attribute: false }) api: WifiApi | undefined;
  @property({ type: String }) locale: Locale = "en";
  @property({ attribute: false }) confirmFunction: (question: string) => boolean = (question) =>
    typeof window === "undefined" ? true : window.confirm(question);

  @state() private wifi: WifiDto | null = null;
  @state() private message = "";
  @state() private isBusy = false;
  @state() private ssid = "";
  @state() private password = "";

  override connectedCallback(): void {
    super.connectedCallback();
    void this.load();
  }

  override render() {
    const strings = uiStrings(this.locale);
    return html`
      <p class="intro">${strings.wifiIntro}</p>
      ${this.renderSaved(strings)} ${this.renderAddForm(strings)}
      ${this.message ? html`<p class="message" role="status">${this.message}</p>` : nothing}
    `;
  }

  private renderSaved(strings: UiStrings): TemplateResult {
    const saved = this.wifi?.saved ?? [];
    return html`
      <section>
        <div class="section-heading">
          <h3>${strings.wifiSavedTitle}</h3>
          <button type="button" class="join" ?disabled=${this.isBusy || saved.length === 0}
            @click=${() => this.requestJoin(strings)}>
            ${strings.wifiJoinNow}
          </button>
        </div>
        ${this.wifi !== null && saved.length === 0 ? html`<p class="empty">${strings.wifiNoneSaved}</p>` : nothing}
        <ul class="saved">
          ${saved.map((network) => this.renderSavedNetwork(strings, network))}
        </ul>
      </section>
    `;
  }

  private renderSavedNetwork(strings: UiStrings, network: SavedWifiNetworkDto): TemplateResult {
    const inRange = this.wifi?.visible.some((visible) => visible.ssid === network.ssid) ?? false;
    return html`
      <li>
        <span class="ssid">${network.ssid}</span>
        ${network.connected
          ? html`<span class="tag connected">${strings.wifiConnected}</span>`
          : inRange
            ? html`<span class="tag">${strings.wifiInRange}</span>`
            : nothing}
        <button type="button" class="forget" ?disabled=${this.isBusy}
          @click=${() => this.forget(strings, network)}>
          ${strings.wifiForget}
        </button>
      </li>
    `;
  }

  private renderAddForm(strings: UiStrings): TemplateResult {
    const savedNames = new Set(this.wifi?.saved.map((network) => network.ssid));
    const suggestions = (this.wifi?.visible ?? []).filter((network) => !savedNames.has(network.ssid));
    return html`
      <form @submit=${(submitEvent: SubmitEvent) => this.save(submitEvent, strings)}>
        <h3>${strings.wifiAddTitle}</h3>
        <label>
          ${strings.wifiSsidLabel}
          <input name="ssid" list="wifi-visible" autocomplete="off" autocapitalize="off" spellcheck="false"
            .value=${this.ssid}
            @input=${(inputEvent: InputEvent) => (this.ssid = (inputEvent.target as HTMLInputElement).value)} />
          <datalist id="wifi-visible">
            ${suggestions.map((network) => html`<option value=${network.ssid}></option>`)}
          </datalist>
        </label>
        <label>
          ${strings.wifiPasswordLabel}
          <input name="password" type="password" autocomplete="new-password" .value=${this.password}
            @input=${(inputEvent: InputEvent) => (this.password = (inputEvent.target as HTMLInputElement).value)} />
          <span class="hint">${strings.wifiPasswordHint}</span>
        </label>
        <button type="submit" class="save" ?disabled=${this.isBusy || !isValidNetwork(this.ssid, this.password)}>
          ${strings.wifiSave}
        </button>
      </form>
    `;
  }

  /** Reads the networks fresh. */
  async load(): Promise<void> {
    await this.run((api) => api.readWifi());
  }

  private async save(submitEvent: SubmitEvent, strings: UiStrings): Promise<void> {
    submitEvent.preventDefault();
    const ssid = this.ssid;
    const saved = await this.run((api) => api.saveWifiNetwork(ssid, this.password));
    if (saved) {
      this.ssid = "";
      this.password = "";
      this.message = strings.wifiSaved.replace("{ssid}", ssid);
    }
  }

  private async forget(strings: UiStrings, network: SavedWifiNetworkDto): Promise<void> {
    if (network.connected && !this.confirmFunction(strings.wifiForgetConnectedConfirm.replaceAll("{ssid}", network.ssid))) {
      return;
    }
    await this.run((api) => api.forgetWifiNetwork(network.ssid));
  }

  private async requestJoin(strings: UiStrings): Promise<void> {
    this.isBusy = true;
    try {
      await this.api?.requestWifiJoin();
      this.message = strings.wifiJoinRequested;
    } catch (caughtError) {
      this.message = wifiErrorMessage(strings, caughtError);
    } finally {
      this.isBusy = false;
    }
  }

  /** Runs one request that answers with the networks, and shows the answer
   * or the failure. Returns whether it worked. */
  private async run(request: (api: WifiApi) => Promise<WifiDto>): Promise<boolean> {
    if (this.api === undefined) {
      return false;
    }
    this.isBusy = true;
    this.message = "";
    try {
      this.wifi = await request(this.api);
      return true;
    } catch (caughtError) {
      this.message = wifiErrorMessage(uiStrings(this.locale), caughtError);
      return false;
    } finally {
      this.isBusy = false;
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "wifi-settings": WifiSettings;
  }
}
