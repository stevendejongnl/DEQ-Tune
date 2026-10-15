import { html, LitElement } from "lit";
import { customElement, property, query, state } from "lit/decorators.js";
import type { BridgeSystemApi, DeviceApi } from "../api/client.ts";
import { BUILD_ID } from "../build-id.ts";
import type { DeviceDto } from "../dto/profile.dto.ts";
import type { Locale } from "../i18n/locale.ts";
import type { AppLayout } from "../layout-query.ts";
import { uiStrings } from "../i18n/ui-strings.ts";
import "./device-pill.ts";
import { deviceStatusStyles } from "./device-status.styles.ts";
import "./system-dialog.ts";
import type { SystemDialog } from "./system-dialog.ts";
import { readLinkState, type LinkState } from "./link-state.ts";

/** How often to ask again, in milliseconds.
 *
 * Faster while the app still expects a change, slower once the link is
 * up and there is nothing to wait for. The backend connects by itself, so
 * this component only watches. It never asks for a connection.
 */
export const POLL_WHILE_DOWN_MS = 3000;
export const POLL_WHILE_UP_MS = 10000;

/** Runs an action after a delay, and returns a handle to cancel it with.
 * `setTimeout` is one such function. A test supplies another. */
export type ScheduleFunction = (action: () => void, delayMs: number) => unknown;

export type CancelFunction = (handle: unknown) => void;

/**
 * Watches the link and hands what it finds to `device-pill`.
 *
 * It reads `/api/device` and asks again on a timer. `app-root` places it
 * in the header. It depends on a `DeviceApi` and on a way to schedule the
 * next read.
 *
 * There is no connect button. The backend connects by itself and keeps
 * trying. The unit sits wired into the car, and both come up with the
 * ignition, so a person has nothing useful to press. This component
 * reports and never asks.
 *
 * A click on the pill opens `system-dialog`, with the Pi's machine
 * statistics and where this page came from.
 *
 * `api` and `scheduleFunction` are settable properties, so a test passes
 * hand-written fakes instead of stubbing anything.
 */
@customElement("device-status")
export class DeviceStatus extends LitElement {
  static override styles = deviceStatusStyles;

  @property({ attribute: false }) api: DeviceApi | undefined;
  @property({ attribute: false }) systemApi: BridgeSystemApi | undefined;
  @property({ type: String }) pageBuild = BUILD_ID;
  @property({ type: String }) locale: Locale = "en";
  @property({ type: String }) layout: AppLayout = "desktop";
  @property({ attribute: false }) scheduleFunction: ScheduleFunction = (
    action,
    delayMs,
  ) => setTimeout(action, delayMs);

  @property({ attribute: false }) cancelFunction: CancelFunction = (handle) =>
    clearTimeout(handle as ReturnType<typeof setTimeout>);

  @state() private device: DeviceDto | null = null;

  @query("system-dialog") private systemDialog!: SystemDialog;

  private pollHandle: unknown;

  override connectedCallback(): void {
    super.connectedCallback();
    void this.readDeviceAndScheduleNext();
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    this.stopPolling();
  }

  get linkState(): LinkState {
    return readLinkState(this.device);
  }

  override render() {
    const strings = uiStrings(this.locale);
    return html`
      <button
        type="button"
        class="open-system"
        aria-haspopup="dialog"
        aria-label=${strings.systemOpenLabel}
        title=${strings.systemOpenLabel}
        @click=${() => void this.systemDialog.show()}
      >
        <device-pill
          .linkState=${this.linkState}
          .firmwareVersion=${this.device?.firmware_version ?? null}
          .locale=${this.locale}
          .layout=${this.layout}
        ></device-pill>
      </button>
      <system-dialog
        .api=${this.systemApi}
        .locale=${this.locale}
        .pageBuild=${this.pageBuild}
        .scheduleFunction=${this.scheduleFunction}
        .cancelFunction=${this.cancelFunction}
      ></system-dialog>
    `;
  }

  private async readDevice(): Promise<void> {
    if (this.api === undefined) {
      return;
    }
    try {
      this.device = await this.api.readDevice();
    } catch {
      // A request that fails outright means the bridge itself is out of
      // reach, which is its own state. A request that succeeds saying
      // `connected: false` is the other case: the bridge answered, and it
      // is the unit that is down.
      this.device = null;
    }
  }

  /** Reads once, tells the app, then asks again after the right gap. */
  private async readDeviceAndScheduleNext(): Promise<void> {
    await this.readDevice();
    this.dispatchEvent(
      new CustomEvent("link-state", {
        detail: { linkState: this.linkState, device: this.device },
      }),
    );
    this.scheduleNextRead();
  }

  private scheduleNextRead(): void {
    this.stopPolling();
    const gap = this.linkState === "connected" ? POLL_WHILE_UP_MS : POLL_WHILE_DOWN_MS;
    this.pollHandle = this.scheduleFunction(() => {
      void this.readDeviceAndScheduleNext();
    }, gap);
  }

  private stopPolling(): void {
    if (this.pollHandle !== undefined) {
      this.cancelFunction(this.pollHandle);
      this.pollHandle = undefined;
    }
  }
}
