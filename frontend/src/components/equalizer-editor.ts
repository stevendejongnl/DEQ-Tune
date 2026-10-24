import { html, LitElement, nothing, type PropertyValues, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
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
 *
 * Undo goes back one edit step (one drag, one tap on − or +), and emits
 * `equalizer-gains` with the curve from before it. A swipe on the phone
 * could move a band by mistake, so the steps are kept until another EQ
 * comes in.
 */
@customElement("equalizer-editor")
export class EqualizerEditor extends LitElement {
  static override styles = equalizerEditorStyles;

  @property({ attribute: false }) equalizer: EqualizerDto | null = null;
  @property({ type: String }) locale: Locale = "en";
  @property({ type: String }) layout: AppLayout = "desktop";

  /** The curve before each edit step, the newest last. */
  @state() private undoSteps: number[][] = [];
  /** True once the current edit step saved its curve to `undoSteps`. */
  private stepSaved = false;

  /** Another EQ drops the steps. The first edit of a factory EQ goes on
   * in its copy: a draft (id -1), then the created EQ. That keeps them. */
  override willUpdate(changed: PropertyValues<this>): void {
    const previous = changed.get("equalizer") as EqualizerDto | null | undefined;
    if (!changed.has("equalizer") || previous === undefined) {
      return;
    }
    const continuesCopy = previous?.id === -1 || this.equalizer?.id === -1;
    if (!continuesCopy && previous?.id !== this.equalizer?.id) {
      this.undoSteps = [];
    }
  }

  override render() {
    const strings = uiStrings(this.locale);
    const equalizer = this.equalizer;
    const gains = equalizer?.gains ?? FLAT;
    return html`
      <section class="panel">
        ${equalizer?.source === "custom"
          ? this.renderOwnHead(strings, equalizer)
          : this.renderReadOnlyHead(strings, equalizer)}
        <div class="undo-row">
          <button type="button" class="undo" ?disabled=${this.undoSteps.length === 0} @click=${() => this.undo()}>
            ${strings.undoEqualizerEdit}
          </button>
        </div>
        <eq-editor
          .heading=${equalizer === null ? strings.noEqualizer : equalizerName(equalizer, this.locale)}
          .gains=${gains}
          .factoryGains=${[]}
          .locale=${this.locale}
          .layout=${this.layout}
          @gain-edit-start=${() => (this.stepSaved = false)}
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
    if (!this.stepSaved) {
      this.undoSteps = [...this.undoSteps, [...gains]];
      this.stepSaved = true;
    }
    this.emit("equalizer-gains", {
      gains: gains.map((gain, index) => (index === band ? value : gain)),
    });
  }

  private undo(): void {
    const previous = this.undoSteps.at(-1);
    if (previous === undefined) {
      return;
    }
    this.undoSteps = this.undoSteps.slice(0, -1);
    this.stepSaved = false;
    this.emit("equalizer-gains", { gains: previous });
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
