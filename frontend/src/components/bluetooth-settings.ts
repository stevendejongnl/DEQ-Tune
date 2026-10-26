import { html, LitElement, nothing, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { BluetoothApi } from "../api/client.ts";
import type { BluetoothPairingDto } from "../dto/profile.dto.ts";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import { bluetoothSettingsStyles } from "./bluetooth-settings.styles.ts";
import { busyStyles } from "./busy.styles.ts";

/** Waits a number of milliseconds. A test passes one that does not wait. */
export type WaitFunction = (milliseconds: number) => Promise<void>;

const waitWithTimer: WaitFunction = (milliseconds) =>
  new Promise((resolve) => setTimeout(resolve, milliseconds));

/** The bridge takes a request within a second, so the section reads the
 * window again this often, a few times, until it shows as open. */
const WINDOW_CHECK_INTERVAL_MS = 1000;
const WINDOW_CHECK_ATTEMPTS = 5;

/**
 * The Bluetooth section of the settings page.
 *
 * The car app reaches the Pi over Bluetooth, and a phone must bond with the
 * Pi first. The Pi lets a new phone bond only while its pairing window is
 * open. This section shows that window and the bonded phones, opens a
 * window with "Pair a new phone", and switches the window at each car start on
 * or off. It depends on a `BluetoothApi`, a `WaitFunction` and a clock.
 */
@customElement("bluetooth-settings")
export class BluetoothSettings extends LitElement {
  static override styles = [bluetoothSettingsStyles, busyStyles];

  @property({ attribute: false }) api: BluetoothApi | undefined;
  @property({ type: String }) locale: Locale = "en";
  @property({ attribute: false }) wait: WaitFunction = waitWithTimer;
  @property({ attribute: false }) now: () => number = () => Date.now();

  @state() private pairing: BluetoothPairingDto | null = null;
  @state() private failed = false;
  @state() private pairBusy = false;
  @state() private pairFailed = false;
  @state() private carStartBusy = false;
  /** When the window ends, in the reader's clock. Set at each read. */
  @state() private openUntil: number | null = null;

  override connectedCallback(): void {
    super.connectedCallback();
    void this.load();
  }

  override render() {
    const strings = uiStrings(this.locale);
    if (this.failed) {
      return html`<p class="hint">${strings.bluetoothFailed}</p>`;
    }
    if (this.pairing === null) {
      return nothing;
    }
    if (!this.pairing.supported) {
      return html`<p class="hint">${strings.bluetoothUnsupported}</p>`;
    }
    return html`
      <p class="intro">${strings.bluetoothIntro}</p>
      ${this.renderWindow(strings)} ${this.renderPairAtCarStart(strings, this.pairing)}
      ${this.renderPhones(strings, this.pairing)}
    `;
  }

  private renderWindow(strings: UiStrings): TemplateResult {
    const status =
      this.openUntil === null
        ? strings.bluetoothClosed
        : strings.bluetoothOpenUntil.replace("{time}", this.formatTime(this.openUntil));
    return html`
      <p class="window ${this.openUntil === null ? "closed" : "open"}" role="status">${status}</p>
      <div class="actions">
        <button type="button" class="pair" ?disabled=${this.pairBusy} aria-busy=${this.pairBusy}
          @click=${() => void this.openWindow()}>
          ${strings.bluetoothPairNew}
        </button>
        ${this.pairFailed ? html`<p class="message" role="alert">${strings.bluetoothPairFailed}</p>` : nothing}
      </div>
    `;
  }

  private renderPairAtCarStart(strings: UiStrings, pairing: BluetoothPairingDto): TemplateResult {
    const minutes = String(Math.round(pairing.window_seconds / 60));
    return html`
      <label class="row" aria-busy=${this.carStartBusy}>
        <span class="row-text">
          <span class="row-label">${strings.bluetoothPairAtCarStart}</span>
          <span class="hint">${strings.bluetoothPairAtCarStartHint.replace("{minutes}", minutes)}</span>
        </span>
        <input type="checkbox" role="switch" name="pair-at-car-start" .checked=${pairing.pair_at_car_start}
          ?disabled=${this.carStartBusy}
          @change=${(changeEvent: Event) =>
            void this.setPairAtCarStart((changeEvent.target as HTMLInputElement).checked)} />
      </label>
    `;
  }

  private renderPhones(strings: UiStrings, pairing: BluetoothPairingDto): TemplateResult {
    if (pairing.bonded_phones.length === 0) {
      return html`<p class="hint phones">${strings.bluetoothNoPhones}</p>`;
    }
    return html`
      <h3>${strings.bluetoothPairedPhones}</h3>
      <ul class="phones">
        ${pairing.bonded_phones.map((phone) => html`<li>${phone}</li>`)}
      </ul>
    `;
  }

  private formatTime(epochMilliseconds: number): string {
    return new Date(epochMilliseconds).toLocaleTimeString(this.locale, { timeStyle: "short" });
  }

  /** Reads the pairing window fresh. */
  async load(): Promise<void> {
    if (this.api === undefined) {
      return;
    }
    try {
      this.show(await this.api.readBluetooth());
      this.failed = false;
    } catch {
      this.failed = true;
    }
  }

  private show(pairing: BluetoothPairingDto): void {
    this.pairing = pairing;
    this.openUntil = pairing.pairing_open ? this.now() + pairing.seconds_left * 1000 : null;
  }

  /** Asks for a window, then reads until the bridge shows it as open. */
  async openWindow(): Promise<void> {
    if (this.api === undefined) {
      return;
    }
    this.pairBusy = true;
    this.pairFailed = false;
    try {
      await this.api.requestPairingWindow();
      for (let attempt = 0; attempt < WINDOW_CHECK_ATTEMPTS; attempt += 1) {
        this.show(await this.api.readBluetooth());
        if (this.pairing?.pairing_open) {
          return;
        }
        await this.wait(WINDOW_CHECK_INTERVAL_MS);
      }
      this.pairFailed = true;
    } catch {
      this.pairFailed = true;
    } finally {
      this.pairBusy = false;
    }
  }

  async setPairAtCarStart(pairAtCarStart: boolean): Promise<void> {
    if (this.api === undefined) {
      return;
    }
    this.carStartBusy = true;
    try {
      this.show(await this.api.setPairAtCarStart(pairAtCarStart));
    } catch {
      // Read again, so the switch shows what the Pi holds.
      await this.load();
    } finally {
      this.carStartBusy = false;
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "bluetooth-settings": BluetoothSettings;
  }
}
