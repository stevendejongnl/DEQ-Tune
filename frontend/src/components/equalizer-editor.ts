import { html, LitElement, type TemplateResult } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { EqualizerDto } from "../dto/profile.dto.ts";
import type { AppLayout } from "../layout-query.ts";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import "./eq-editor.ts";
import { equalizerEditorStyles } from "./equalizer-editor.styles.ts";

/**
 * Edits one EQ of the person's own: its name and its curve.
 *
 * Set `equalizer`, `locale` and `layout`. It emits `equalizer-change`
 * ({ id, name } or { id, gains }) on every edit, `delete-equalizer`
 * ({ id }) and `close-editor`. It reads no API. app-root saves each change.
 *
 * The curve editor is the one the car profile uses. An EQ has no factory
 * curve to compare with, so the chart draws its curve alone.
 */
@customElement("equalizer-editor")
export class EqualizerEditor extends LitElement {
  static override styles = equalizerEditorStyles;

  @property({ attribute: false }) equalizer: EqualizerDto | null = null;
  @property({ type: String }) locale: Locale = "en";
  @property({ type: String }) layout: AppLayout = "desktop";

  override render() {
    const equalizer = this.equalizer;
    if (equalizer === null) {
      return html``;
    }
    const strings = uiStrings(this.locale);
    return html`
      <section class="panel">
        ${this.renderHead(strings, equalizer)}
        <eq-editor
          .gains=${equalizer.gains}
          .factoryGains=${[]}
          .locale=${this.locale}
          .layout=${this.layout}
          @gain-change=${(gainChangeEvent: CustomEvent<{ band: number; value: number }>) =>
            this.changeGain(equalizer, gainChangeEvent.detail.band, gainChangeEvent.detail.value)}
        ></eq-editor>
      </section>
    `;
  }

  private renderHead(strings: UiStrings, equalizer: EqualizerDto): TemplateResult {
    return html`
      <div class="head">
        <label class="name">
          <span>${strings.equalizerNameLabel}</span>
          <input
            type="text"
            .value=${equalizer.name}
            @change=${(event: Event) =>
              this.changeName(equalizer, (event.target as HTMLInputElement).value)}
          />
        </label>
        <div class="actions">
          <button
            type="button"
            class="delete"
            @click=${() => this.emit("delete-equalizer", { id: equalizer.id })}
          >
            ${strings.deleteEqualizer}
          </button>
          <button type="button" class="done" @click=${() => this.emit("close-editor", {})}>
            ${strings.doneEditing}
          </button>
        </div>
      </div>
    `;
  }

  private changeGain(equalizer: EqualizerDto, band: number, value: number): void {
    const gains = equalizer.gains.map((gain, index) => (index === band ? value : gain));
    this.emit("equalizer-change", { id: equalizer.id, gains });
  }

  /** An emptied name keeps the old one. */
  private changeName(equalizer: EqualizerDto, typed: string): void {
    const name = typed.trim();
    if (name === "" || name === equalizer.name) {
      return;
    }
    this.emit("equalizer-change", { id: equalizer.id, name });
  }

  private emit(type: string, detail: object): void {
    this.dispatchEvent(new CustomEvent(type, { detail }));
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "equalizer-editor": EqualizerEditor;
  }
}
