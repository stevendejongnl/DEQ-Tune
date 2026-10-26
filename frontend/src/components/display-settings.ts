import { html, LitElement, type TemplateResult } from "lit";
import { customElement, property } from "lit/decorators.js";
import { displayController, type DisplayController } from "../display/display-controller.ts";
import type { DisplayChoices } from "../display/display-mode.ts";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings } from "../i18n/ui-strings.ts";
import { displaySettingsStyles } from "./display-settings.styles.ts";

type Option<Value extends string> = { value: Value; label: string };

/**
 * The Display section of the settings page: colours, contrast, text size
 * and reading.
 *
 * Each choice applies at once and stays on this device. It depends on a
 * `DisplayController`, which a test replaces.
 */
@customElement("display-settings")
export class DisplaySettings extends LitElement {
  static override styles = displaySettingsStyles;

  @property({ attribute: false }) controller: DisplayController = displayController;
  @property({ type: String }) locale: Locale = "en";

  override render() {
    const strings = uiStrings(this.locale);
    const choices = this.controller.choices;
    return html`
      <p class="hint">${strings.displayIntro}</p>
      ${this.renderChoice("scheme", strings.displaySchemeLabel, choices.scheme, [
        { value: "device", label: strings.displayFollowDevice },
        { value: "dark", label: strings.displaySchemeDark },
        { value: "light", label: strings.displaySchemeLight },
      ])}
      ${this.renderChoice("contrast", strings.displayContrastLabel, choices.contrast, [
        { value: "device", label: strings.displayFollowDevice },
        { value: "normal", label: strings.displayNormal },
        { value: "more", label: strings.displayContrastMore },
      ])}
      ${this.renderChoice("text", strings.displayTextLabel, choices.text, [
        { value: "device", label: strings.displayFollowDevice },
        { value: "normal", label: strings.displayNormal },
        { value: "large", label: strings.displayTextLarge },
      ])}
      ${this.renderChoice("reading", strings.displayReadingLabel, choices.reading, [
        { value: "normal", label: strings.displayNormal },
        { value: "easy", label: strings.displayReadingEasy },
      ])}
      <p class="hint">${strings.displayReadingHint}</p>
    `;
  }

  private renderChoice<Key extends keyof DisplayChoices>(
    key: Key,
    label: string,
    current: DisplayChoices[Key],
    options: Option<DisplayChoices[Key]>[],
  ): TemplateResult {
    return html`
      <label class="row">
        <span class="row-label">${label}</span>
        <select name=${key}
          @change=${(changeEvent: Event) =>
            this.choose(key, (changeEvent.target as HTMLSelectElement).value as DisplayChoices[Key])}>
          ${options.map(
            (option) => html`<option value=${option.value} ?selected=${option.value === current}>${option.label}</option>`,
          )}
        </select>
      </label>
    `;
  }

  choose<Key extends keyof DisplayChoices>(key: Key, value: DisplayChoices[Key]): void {
    this.controller.choose({ [key]: value } as Partial<DisplayChoices>);
    this.requestUpdate();
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "display-settings": DisplaySettings;
  }
}
