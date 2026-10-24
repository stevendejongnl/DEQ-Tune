import { html, LitElement, nothing, type TemplateResult } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { Locale } from "../i18n/locale.ts";
import type { AppLayout } from "../layout-query.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import { devicePillStyles } from "./device-pill.styles.ts";
import type { LinkState } from "./link-state.ts";

/**
 * The header's status pill: a dot, what the link is doing, and whether
 * the page is live. The unit's firmware version is in Settings → System.
 *
 * It shows one link state and nothing else. `device-status` sets its
 * properties. It depends only on the UI strings. It reads no API and
 * holds no state of its own, so it renders the same way for the same
 * inputs every time.
 *
 * `linkState` is a plain attribute so the stylesheet can select on it,
 * which keeps the dot's colour in CSS rather than in a class list built
 * by the template.
 */
@customElement("device-pill")
export class DevicePill extends LitElement {
  static override styles = devicePillStyles;

  @property({ type: String, reflect: true }) linkState: LinkState = "no-bridge";
  @property({ type: String }) locale: Locale = "en";
  @property({ type: String }) layout: AppLayout = "desktop";

  /** The phone header has room for the dot alone, so it drops the status
   * text until a unit connects. */
  private get showsLabel(): boolean {
    return this.linkState === "connected" || this.layout !== "phone";
  }

  override render() {
    const strings = uiStrings(this.locale);
    return html`
      <span class="dot"></span>
      ${this.showsLabel ? this.renderLabel(strings) : nothing}
      ${this.renderFreshness(strings)}
    `;
  }

  /** Whether the Pi answers this page, or the page is offline: no bridge
   * means that no server answered, and the page shows what it had. */
  private renderFreshness(strings: UiStrings): TemplateResult {
    const isOffline = this.linkState === "no-bridge";
    return html`<span class="freshness">${isOffline ? strings.pageOffline : strings.pageLive}</span>`;
  }

  private renderLabel(strings: UiStrings): TemplateResult {
    if (this.linkState === "no-bridge") {
      return html`<span class="device-label">${strings.bridgeUnreachable}</span>`;
    }
    if (this.linkState === "unit-down") {
      return html`<span class="device-label">${strings.deviceNotConnected}</span>`;
    }
    return html`<span class="device-label">${strings.deviceConnected}</span>`;
  }
}
