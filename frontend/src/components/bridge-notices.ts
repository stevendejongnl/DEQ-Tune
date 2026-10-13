import { html, LitElement, nothing, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { BridgeApi } from "../api/client.ts";
import type { BridgeNoticeDto } from "../dto/profile.dto.ts";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings } from "../i18n/ui-strings.ts";
import { bridgeNoticesStyles } from "./bridge-notices.styles.ts";

/** How often to ask the bridge how it is, in milliseconds.
 *
 * Slower than the device poll. A notice stays once raised, so a slower
 * poll misses nothing, and the answer rarely changes.
 */
export const BRIDGE_POLL_MS = 30000;

export const WARNING_SEVERITY = "warning";

/** Runs an action after a delay, and returns a handle to cancel it with.
 * `setTimeout` is one such function. A test supplies another. */
export type ScheduleFunction = (action: () => void, delayMs: number) => unknown;

export type CancelFunction = (handle: unknown) => void;

/**
 * Shows what has gone wrong on the machine holding the link.
 *
 * It renders nothing at all while the bridge is well. `app-root` places
 * it in the header. It depends on a `BridgeApi` and a way to schedule
 * the next read.
 *
 * A notice stays raised until the bridge restarts, so the component can
 * show a fault that is no longer happening. It does so on purpose. A power
 * dip lasting a second drops the USB link and the Wi-Fi. By the time
 * anyone looks, every live reading is healthy again.
 */
@customElement("bridge-notices")
export class BridgeNotices extends LitElement {
  static override styles = bridgeNoticesStyles;

  @property({ attribute: false }) api: BridgeApi | undefined;
  @property({ type: String }) locale: Locale = "en";
  @property({ attribute: false }) scheduleFunction: ScheduleFunction = (
    action,
    delayMs,
  ) => setTimeout(action, delayMs);

  @property({ attribute: false }) cancelFunction: CancelFunction = (handle) =>
    clearTimeout(handle as ReturnType<typeof setTimeout>);

  @state() private notices: BridgeNoticeDto[] = [];
  @state() private isDismissed = false;

  private pollHandle: unknown;

  override connectedCallback(): void {
    super.connectedCallback();
    void this.readBridgeAndScheduleNext();
  }

  override disconnectedCallback(): void {
    super.disconnectedCallback();
    this.stopPolling();
  }

  get warnings(): BridgeNoticeDto[] {
    return this.notices.filter((notice) => notice.severity === WARNING_SEVERITY);
  }

  override render() {
    if (this.isDismissed || this.warnings.length === 0) {
      return nothing;
    }
    return html`
      <div class="notices" role="status">
        ${this.warnings.map((notice) => this.renderNotice(notice))}
        ${this.renderDismissButton()}
      </div>
    `;
  }

  private renderNotice(notice: BridgeNoticeDto): TemplateResult {
    return html`
      <div class="notice">
        <span class="message" title=${notice.message}>${notice.message}</span>
        ${notice.count > 1
          ? html`<span class="count">×${notice.count}</span>`
          : nothing}
      </div>
    `;
  }

  private renderDismissButton(): TemplateResult {
    const strings = uiStrings(this.locale);
    return html`
      <button
        type="button"
        class="dismiss"
        title=${strings.bridgeNoticeDismissHint}
        aria-label=${strings.dismiss}
        @click=${() => (this.isDismissed = true)}
      >
        ×
      </button>
    `;
  }

  private async readBridge(): Promise<void> {
    if (this.api === undefined) {
      return;
    }
    try {
      this.notices = (await this.api.readBridge()).notices;
    } catch {
      // The device pill already reports a bridge out of reach, so this
      // component stays quiet rather than saying the same thing twice. It
      // keeps the notices it has: they describe what happened before.
    }
  }

  private async readBridgeAndScheduleNext(): Promise<void> {
    await this.readBridge();
    this.scheduleNextRead();
  }

  private scheduleNextRead(): void {
    this.stopPolling();
    this.pollHandle = this.scheduleFunction(() => {
      void this.readBridgeAndScheduleNext();
    }, BRIDGE_POLL_MS);
  }

  private stopPolling(): void {
    if (this.pollHandle !== undefined) {
      this.cancelFunction(this.pollHandle);
      this.pollHandle = undefined;
    }
  }
}
