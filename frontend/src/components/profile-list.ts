import { html, LitElement, nothing, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { ProfileDto } from "../dto/profile.dto.ts";
import type { Locale } from "../i18n/locale.ts";
import { localizedProfileName } from "../i18n/preset-names.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import { groupFactoryProfiles, type CarModelGroup } from "../factory-groups.ts";
import { autoFocus } from "./auto-focus.ts";
import { profileListStyles } from "./profile-list.styles.ts";

function renderSearchIcon(): TemplateResult {
  return html`
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
      <circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" stroke-width="1.5" />
      <path d="M10.5 10.5 L14 14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
    </svg>
  `;
}

/**
 * The profile list: a search field, your own profiles, and the factory
 * presets grouped by car model. Each model row offers a Pioneer chip
 * and a Stock chip, which map to the two speaker types.
 *
 * It emits `select-profile` ({ id }), `duplicate-profile` ({ id }) and
 * `delete-profile` ({ id }).
 */
@customElement("profile-list")
export class ProfileList extends LitElement {
  static override styles = profileListStyles;

  @property({ type: Array }) profiles: ProfileDto[] = [];
  @property({ type: Number }) selectedId: number | null = null;
  @property({ type: String }) locale: Locale = "en";
  /** Only a connected unit has a tune to save. */
  @property({ type: Boolean }) unitConnected = false;

  @state() private search = "";
  @state() private openMenuId: number | null = null;
  @state() private renamingId: number | null = null;

  override render() {
    const strings = uiStrings(this.locale);
    const customProfiles = this.profiles.filter((profile) => profile.source === "custom");
    const groups = groupFactoryProfiles(this.profiles, this.locale, this.search);
    return html`
      ${this.renderSearchField(strings)} ${this.renderCustomSection(strings, customProfiles)}
      ${this.renderFactorySection(strings, groups)}
    `;
  }

  private renderSearchField(strings: UiStrings): TemplateResult {
    return html`
      <label class="search">
        ${renderSearchIcon()}
        <span class="visually-hidden">${strings.findYourCar}</span>
        <input
          type="search"
          placeholder=${strings.findYourCar}
          .value=${this.search}
          @input=${(event: Event) => (this.search = (event.target as HTMLInputElement).value)}
        />
      </label>
    `;
  }

  private renderCustomSection(
    strings: UiStrings,
    customProfiles: readonly ProfileDto[],
  ): TemplateResult {
    return html`
      <section class="group">
        <div class="group-head">
          <h3 class="group-label">${strings.myProfiles}</h3>
          <div class="head-actions">
            ${this.unitConnected
              ? html`
                  <button
                    type="button"
                    class="head-action save-unit-tune"
                    @click=${() => this.dispatchEvent(new CustomEvent("save-unit-profile"))}
                  >
                    ${strings.saveUnitTune}
                  </button>
                `
              : nothing}
            <button
              type="button"
              class="head-action new-profile"
              @click=${() => this.dispatchEvent(new CustomEvent("create-profile"))}
            >
              + ${strings.newProfile}
            </button>
          </div>
        </div>
        ${customProfiles.length === 0
          ? html`<p class="empty">${strings.duplicateHint}</p>`
          : html`
              <ul class="custom-list">
                ${customProfiles.map((profile) => this.renderCustomProfile(strings, profile))}
              </ul>
            `}
      </section>
    `;
  }

  private renderCustomProfile(strings: UiStrings, profile: ProfileDto): TemplateResult {
    if (this.renamingId === profile.id) {
      return this.renderRenameRow(strings, profile);
    }
    return html`
      <li class="custom-row ${profile.id === this.selectedId ? "selected" : ""}">
        <button class="name" type="button" @click=${() => this.selectProfile(profile.id)}>
          <span class="custom-name">${localizedProfileName(profile, this.locale)}</span>
          <span class="custom-caption">${strings.customProfileCaption}</span>
        </button>
        <button
          class="more"
          type="button"
          aria-label=${strings.moreActionsLabel}
          aria-expanded=${this.openMenuId === profile.id}
          @click=${() => this.toggleMenu(profile.id)}
        >
          ⋯
        </button>
        ${this.openMenuId === profile.id
          ? html`
              <div class="menu">
                <button class="action" type="button" @click=${() => this.startRename(profile.id)}>
                  ${strings.rename}
                </button>
                <button
                  class="action"
                  type="button"
                  @click=${() => this.duplicateProfile(profile.id)}
                >
                  ${strings.duplicate}
                </button>
                <button
                  class="action destructive"
                  type="button"
                  @click=${() => this.deleteProfile(profile.id)}
                >
                  ${strings.delete}
                </button>
              </div>
            `
          : nothing}
      </li>
    `;
  }

  /** Renaming swaps the row for one text field. Enter keeps the name
   * and Escape drops the change. */
  private renderRenameRow(strings: UiStrings, profile: ProfileDto): TemplateResult {
    return html`
      <li class="custom-row renaming">
        <input
          class="rename-input"
          type="text"
          .value=${profile.name}
          aria-label=${strings.renameLabel}
          @keydown=${(event: KeyboardEvent) => this.onRenameKeydown(event, profile.id)}
          @blur=${(event: Event) => this.commitRename(profile.id, event.target as HTMLInputElement)}
          ${autoFocus()}
        />
      </li>
    `;
  }

  private renderFactorySection(
    strings: UiStrings,
    groups: readonly CarModelGroup[],
  ): TemplateResult {
    const brand = groups[0]?.brand ?? null;
    return html`
      <section class="group">
        <h3 class="group-label">
          ${strings.factoryGroupLabel}${brand === null ? nothing : ` · ${brand}`}
        </h3>
        <ul class="factory-list">
          ${groups.map((group) => this.renderModelRow(strings, group))}
        </ul>
      </section>
    `;
  }

  private renderModelRow(strings: UiStrings, group: CarModelGroup): TemplateResult {
    const holdsSelection = group.profiles.some((profile) => profile.id === this.selectedId);
    return html`
      <li class="model-row ${holdsSelection ? "selected" : ""}">
        <span class="model-name">${group.modelName}</span>
        <div class="chips">
          ${this.renderSpeakerChip(group, "carrozzeria", strings.speakerPioneerShort)}
          ${this.renderSpeakerChip(group, "general", strings.speakerStockShort)}
        </div>
      </li>
    `;
  }

  private renderSpeakerChip(
    group: CarModelGroup,
    speakerType: string,
    label: string,
  ): TemplateResult {
    const profile = group.profiles.find((candidate) => candidate.speaker_type === speakerType);
    if (profile === undefined) {
      return html``;
    }
    const selected = profile.id === this.selectedId;
    return html`
      <button
        type="button"
        class="chip ${selected ? "selected" : ""}"
        aria-pressed=${selected}
        @click=${() => this.selectProfile(profile.id)}
      >
        ${label}
      </button>
    `;
  }

  private startRename(id: number): void {
    this.openMenuId = null;
    this.renamingId = id;
  }

  private onRenameKeydown(event: KeyboardEvent, id: number): void {
    if (event.key === "Enter") {
      this.commitRename(id, event.target as HTMLInputElement);
      return;
    }
    if (event.key === "Escape") {
      this.renamingId = null;
    }
  }

  private commitRename(id: number, input: HTMLInputElement): void {
    if (this.renamingId !== id) {
      return;
    }
    this.renamingId = null;
    const name = input.value.trim();
    if (name === "") {
      return;
    }
    this.dispatchEvent(new CustomEvent("rename-profile", { detail: { id, name } }));
  }

  private toggleMenu(id: number): void {
    this.openMenuId = this.openMenuId === id ? null : id;
  }

  private selectProfile(id: number) {
    this.openMenuId = null;
    this.dispatchEvent(new CustomEvent("select-profile", { detail: { id } }));
  }

  private duplicateProfile(id: number) {
    this.openMenuId = null;
    this.dispatchEvent(new CustomEvent("duplicate-profile", { detail: { id } }));
  }

  private deleteProfile(id: number) {
    this.openMenuId = null;
    this.dispatchEvent(new CustomEvent("delete-profile", { detail: { id } }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "profile-list": ProfileList;
  }
}
