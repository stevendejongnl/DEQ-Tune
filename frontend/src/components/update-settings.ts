import { html, LitElement, nothing, type TemplateResult } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { UpdatesDto } from "../dto/profile.dto.ts";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import { updateSettingsStyles } from "./update-settings.styles.ts";
import { busyStyles } from "./busy.styles.ts";
import type { UpdateRequestState } from "./updates-controller.ts";

/** A timestamp from the updater, in the reader's own clock and language. */
function formatCheckedAt(checkedAt: string, locale: Locale): string {
  const time = new Date(checkedAt);
  return Number.isNaN(time.getTime())
    ? checkedAt
    : time.toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" });
}

/**
 * The Updates section of the settings page.
 *
 * It shows the installed and the latest release, the last check, and the
 * switch for automatic updates. Presentational: it fires
 * `automatic-change` ({ automatic }) and `request-update`, and app-root
 * does the talking through its updates controller.
 */
@customElement("update-settings")
export class UpdateSettings extends LitElement {
  static override styles = [updateSettingsStyles, busyStyles];

  @property({ attribute: false }) updates: UpdatesDto | null = null;
  @property({ type: String }) requestState: UpdateRequestState = "idle";
  @property({ type: String }) locale: Locale = "en";

  override render() {
    const strings = uiStrings(this.locale);
    const updates = this.updates;
    if (updates === null) {
      return html`<p class="hint">${strings.updatesFailed}</p>`;
    }
    if (!updates.supported) {
      return html`<p class="hint">${strings.updatesUnsupported}</p>`;
    }
    return html`
      <p class="intro">${strings.updatesIntro}</p>
      ${this.renderVersions(strings, updates)} ${this.renderAutomatic(strings, updates)}
      ${this.renderCheckNow(strings)} ${this.renderHistory(strings, updates)}
    `;
  }

  private renderVersions(strings: UiStrings, updates: UpdatesDto): TemplateResult {
    return html`
      <dl class="versions">
        <dt>${strings.updatesInstalled}</dt>
        <dd class="installed">${updates.installed ?? "–"}</dd>
        <dt>${strings.updatesLatest}</dt>
        <dd class="latest">
          ${updates.latest ?? "–"}
          ${updates.release_url
            ? html`<a href=${updates.release_url} target="_blank" rel="noopener">${strings.updatesChangelog}</a>`
            : nothing}
        </dd>
        <dt>${strings.updatesChecked}</dt>
        <dd>${updates.checked_at ? formatCheckedAt(updates.checked_at, this.locale) : strings.updatesNever}</dd>
        <dt>${strings.updatesLastResult}</dt>
        <dd class="last-result">${updates.last_result || "–"}</dd>
      </dl>
      ${updates.gadget_pending ? html`<p class="hint">${strings.updatesGadgetPending}</p>` : nothing}
    `;
  }

  private renderAutomatic(strings: UiStrings, updates: UpdatesDto): TemplateResult {
    return html`
      <label class="row">
        <span class="row-text">
          <span class="row-label">${strings.updatesAutomatic}</span>
          <span class="hint">${strings.updatesAutomaticHint}</span>
        </span>
        <input
          type="checkbox"
          role="switch"
          name="automatic"
          .checked=${updates.automatic}
          @change=${(changeEvent: Event) =>
            this.fire("automatic-change", { automatic: (changeEvent.target as HTMLInputElement).checked })}
        />
      </label>
    `;
  }

  private renderCheckNow(strings: UiStrings): TemplateResult {
    const message = {
      idle: "",
      busy: "",
      requested: strings.updatesRequested,
      failed: strings.updatesFailed,
      unsupported: strings.updatesUnsupported,
    }[this.requestState];
    return html`
      <div class="actions">
        <button type="button" class="check-now" ?disabled=${this.requestState === "busy"}
          aria-busy=${this.requestState === "busy"}
          @click=${() => this.fire("request-update", {})}>
          ${strings.updatesCheckNow}
        </button>
        ${message ? html`<p class="message" role="status">${message}</p>` : nothing}
      </div>
    `;
  }

  private renderHistory(strings: UiStrings, updates: UpdatesDto): TemplateResult | typeof nothing {
    if (updates.history.length === 0) {
      return nothing;
    }
    return html`
      <h3>${strings.updatesHistory}</h3>
      <ul class="history">
        ${updates.history.map(
          (entry) => html`<li>${entry.from_version} → ${entry.to_version}
            <span class="hint">${formatCheckedAt(entry.at, this.locale)}</span></li>`,
        )}
      </ul>
    `;
  }

  private fire(name: string, detail: object): void {
    this.dispatchEvent(new CustomEvent(name, { detail, bubbles: true, composed: true }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "update-settings": UpdateSettings;
  }
}
