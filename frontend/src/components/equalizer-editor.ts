import { html, LitElement, nothing, type TemplateResult } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { EqualizerDto } from "../dto/profile.dto.ts";
import type { AppLayout } from "../layout-query.ts";
import type { Locale } from "../i18n/locale.ts";
import { equalizerName } from "../i18n/equalizer-names.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import "./eq-editor.ts";
import { equalizerEditorStyles } from "./equalizer-editor.styles.ts";

const FLAT = new Array(13).fill(0);

/**
 * The EQ that plays, as one curve to edit. It is the main EQ of the app.
 * The car profile's own correction curve sits with the car settings.
 *
 * Set `equalizer` (`null` for No EQ), `locale` and `layout`. It emits
 * `equalizer-gains` ({ gains }) on every curve edit, `rename-equalizer`
 * ({ name }) and `delete-equalizer` ({ id }). It reads no API.
 *
 * Any EQ can take a drag. An EQ of the person's own changes in place. A
 * factory EQ and No EQ say that a drag makes a copy, and app-root makes it.
 */
@customElement("equalizer-editor")
export class EqualizerEditor extends LitElement {
  static override styles = equalizerEditorStyles;

  @property({ attribute: false }) equalizer: EqualizerDto | null = null;
  @property({ type: String }) locale: Locale = "en";
  @property({ type: String }) layout: AppLayout = "desktop";

  override render() {
    const strings = uiStrings(this.locale);
    const equalizer = this.equalizer;
    const gains = equalizer?.gains ?? FLAT;
    return html`
      <section class="panel">
        ${equalizer?.source === "custom"
          ? this.renderOwnHead(strings, equalizer)
          : this.renderReadOnlyHead(strings, equalizer)}
        <eq-editor
          .heading=${equalizer === null ? strings.noEqualizer : equalizerName(equalizer, this.locale)}
          .gains=${gains}
          .factoryGains=${[]}
          .locale=${this.locale}
          .layout=${this.layout}
          @gain-change=${(gainChangeEvent: CustomEvent<{ band: number; value: number }>) =>
            this.changeGain(gains, gainChangeEvent.detail.band, gainChangeEvent.detail.value)}
        ></eq-editor>
      </section>
    `;
  }

  private renderOwnHead(strings: UiStrings, equalizer: EqualizerDto): TemplateResult {
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
        ${equalizer.id < 0
          ? nothing
          : html`
              <div class="actions">
                <button
                  type="button"
                  class="delete"
                  @click=${() => this.emit("delete-equalizer", { id: equalizer.id })}
                >
                  ${strings.deleteEqualizer}
                </button>
              </div>
            `}
      </div>
    `;
  }

  private renderReadOnlyHead(strings: UiStrings, equalizer: EqualizerDto | null): TemplateResult {
    return html`
      <p class="hint">${equalizer === null ? strings.noEqualizerHint : strings.factoryEqualizerHint}</p>
    `;
  }

  private changeGain(gains: readonly number[], band: number, value: number): void {
    this.emit("equalizer-gains", {
      gains: gains.map((gain, index) => (index === band ? value : gain)),
    });
  }

  /** An emptied name keeps the old one. */
  private changeName(equalizer: EqualizerDto, typed: string): void {
    const name = typed.trim();
    if (name === "" || name === equalizer.name) {
      return;
    }
    this.emit("rename-equalizer", { name });
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
