import { html, LitElement, nothing, type TemplateResult } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { ActiveProfileDto } from "../dto/profile.dto.ts";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import { profileActivationStyles } from "./profile-activation.styles.ts";
import { busyStyles } from "./busy.styles.ts";

/**
 * Says whether the shown profile is the one the unit plays, and offers to
 * make it so.
 *
 * Set `profileId`, `active` (what the backend reports), `hasDraft` and
 * `locale`. It emits `activate-profile` ({ id }) for Activate, Apply changes
 * and Try again: each asks the backend to push the profile. It reads no API.
 *
 * A draft is an edit that only lives on screen. The backend pushes the stored
 * profile, so Activate waits until the person saves the draft.
 */
@customElement("profile-activation")
export class ProfileActivation extends LitElement {
  static override styles = [profileActivationStyles, busyStyles];

  @property({ type: Number }) profileId: number | null = null;
  @property({ attribute: false }) active: ActiveProfileDto | null = null;
  @property({ type: Boolean }) hasDraft = false;
  @property({ type: Boolean }) busy = false;
  @property({ type: String }) locale: Locale = "en";

  override render() {
    const strings = uiStrings(this.locale);
    if (this.active === null || this.profileId === null) {
      return nothing;
    }
    if (this.active.profile_id !== this.profileId) {
      return this.renderActivate(strings);
    }
    return this.renderStatus(strings, this.active);
  }

  private renderActivate(strings: UiStrings): TemplateResult {
    return html`
      <button
        type="button"
        class="activate"
        ?disabled=${this.hasDraft || this.busy}
        aria-busy=${this.busy}
        @click=${() => this.requestActivation()}
      >
        ${strings.activate}
      </button>
      ${this.hasDraft ? html`<span class="hint">${strings.saveBeforeActivate}</span>` : nothing}
    `;
  }

  private renderStatus(strings: UiStrings, active: ActiveProfileDto): TemplateResult {
    switch (active.status) {
      case "applied":
        return this.renderLine("applied", strings.activeApplied);
      case "waiting":
        return this.renderLine("waiting", strings.activeWaiting);
      case "outdated":
        return this.renderLine("outdated", strings.activeOutdated, strings.applyChanges);
      case "failed":
        return this.renderLine(
          "failed",
          `${strings.activeFailed}${active.problem === null ? "" : `: ${active.problem}`}`,
          strings.tryAgain,
        );
      default:
        return html``;
    }
  }

  private renderLine(kind: string, text: string, actionLabel?: string): TemplateResult {
    return html`
      <span class="status ${kind}" role="status"><span class="dot" aria-hidden="true"></span>${text}</span>
      ${actionLabel === undefined
        ? nothing
        : html`
            <button
              type="button"
              class="apply"
              ?disabled=${this.hasDraft || this.busy}
              aria-busy=${this.busy}
              @click=${() => this.requestActivation()}
            >
              ${actionLabel}
            </button>
          `}
    `;
  }

  private requestActivation(): void {
    this.dispatchEvent(new CustomEvent("activate-profile", { detail: { id: this.profileId } }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "profile-activation": ProfileActivation;
  }
}
