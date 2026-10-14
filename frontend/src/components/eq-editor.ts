import { html, LitElement, nothing, svg, type SVGTemplateResult, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { EQ_BAND_FREQUENCIES } from "../eq-bands.ts";
import {
  areaPath,
  bandX,
  clampGain,
  curvePoints,
  gainFromY,
  formatGain,
  fullFrequencyLabel,
  gainY,
  gridPath,
  shortFrequencyLabel,
  smoothCurvePath,
  zeroLinePath,
  GAIN_STEP_DB,
  MAX_GAIN_DB,
  MIN_GAIN_DB,
  type ChartBox,
} from "../eq-curve.ts";
import { EQ_ZONES, zoneHint, zoneName, zoneOfBand, type EqZone } from "../eq-zones.ts";
import type { AppLayout } from "../layout-query.ts";
import type { Locale } from "../i18n/locale.ts";
import { uiStrings, type UiStrings } from "../i18n/ui-strings.ts";
import { eqEditorStyles } from "./eq-editor.styles.ts";

const LAST_BAND = EQ_BAND_FREQUENCIES.length - 1;

/** Chart height and padding per layout. The width comes from a
 * `ResizeObserver`, so the chart follows its panel. */
const CHART_SHAPES: Record<AppLayout, Omit<ChartBox, "width">> = {
  desktop: { height: 300, padLeft: 36, padRight: 16, padY: 24 },
  tablet: { height: 280, padLeft: 36, padRight: 20, padY: 22 },
  phone: { height: 220, padLeft: 30, padRight: 10, padY: 16 },
};

const FALLBACK_WIDTH: Record<AppLayout, number> = {
  desktop: 640,
  tablet: 720,
  phone: 358,
};

/** The phone chart is too short for five labels. */
const AXIS_GAINS: Record<AppLayout, readonly number[]> = {
  desktop: [12, 6, 0, -6, -12],
  tablet: [12, 6, 0, -6, -12],
  phone: [12, 0, -12],
};

function chartBox(layout: AppLayout, measuredWidth: number): ChartBox {
  return {
    ...CHART_SHAPES[layout],
    width: measuredWidth > 0 ? measuredWidth : FALLBACK_WIDTH[layout],
  };
}

function renderAxisLabels(box: ChartBox, layout: AppLayout): SVGTemplateResult[] {
  return AXIS_GAINS[layout].map(
    (gain) => svg`
      <text
        class="axis-label"
        x=${gain === 0 ? 8 : Math.abs(gain) === 6 ? 4 : 0}
        y=${gainY(box, gain) + 4}
      >${formatAxisGain(gain)}</text>
    `,
  );
}

function formatAxisGain(gain: number): string {
  if (gain === 0) {
    return "0";
  }
  return gain > 0 ? `+${gain}` : `−${Math.abs(gain)}`;
}

/** The left and the right edge of a zone, halfway between its
 * neighbouring bands. The first and the last zone reach the chart
 * edges. */
function zoneEdges(box: ChartBox, zone: EqZone): { left: number; right: number } {
  const left =
    zone.index === 0
      ? box.padLeft - 12
      : (bandX(box, zone.firstBand - 1) + bandX(box, zone.firstBand)) / 2;
  const lastPairedBand = Math.min(LAST_BAND, zone.firstBand + 1);
  const right =
    zone.index === EQ_ZONES.length - 1
      ? box.width - 4
      : (bandX(box, lastPairedBand) + bandX(box, lastPairedBand + 1)) / 2;
  return { left, right };
}

/**
 * The frequency-response chart for one channel. It draws your curve
 * over the factory curve, and edits one band at a time.
 *
 * Set `gains`, `factoryGains`, `locale` and `layout`. It emits
 * `gain-change` with `{ band, value }` on every edit. It depends on
 * `ResizeObserver` for the chart width.
 */
@customElement("eq-editor")
export class EqEditor extends LitElement {
  static override styles = eqEditorStyles;

  @property({ type: Array }) gains: number[] = [];
  @property({ type: Array }) factoryGains: number[] = [];
  @property({ type: String }) locale: Locale = "en";
  @property({ type: String }) layout: AppLayout = "desktop";

  @state() private selectedBand = LAST_BAND;
  @state() private chartWidth = 0;

  private resizeObserver: ResizeObserver | null = null;
  private draggingBand: number | null = null;

  override disconnectedCallback() {
    super.disconnectedCallback();
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
  }

  override firstUpdated() {
    const frame = this.shadowRoot?.querySelector(".chart-frame");
    if (frame === null || frame === undefined || typeof ResizeObserver === "undefined") {
      return;
    }
    this.resizeObserver = new ResizeObserver((entries) => {
      this.chartWidth = entries[0].contentRect.width;
    });
    this.resizeObserver.observe(frame);
  }

  private gainOf(band: number): number {
    return this.gains[band] ?? 0;
  }

  private factoryGainOf(band: number): number | null {
    return this.factoryGains[band] ?? null;
  }

  private isChanged(band: number): boolean {
    const factory = this.factoryGainOf(band);
    return factory !== null && factory !== this.gainOf(band);
  }

  override render() {
    const strings = uiStrings(this.locale);
    const box = chartBox(this.layout, this.chartWidth);
    return html`
      <section class="panel">
        <div class="panel-head">
          <h2>${strings.frequencyResponseTitle}</h2>
          <div class="legend">
            <span class="legend-entry"><span class="swatch yours"></span>${strings.legendYours}</span>
            ${this.factoryGains.length === 0
              ? nothing
              : html`<span class="legend-entry"
                  ><span class="swatch factory"></span>${strings.legendFactory}</span
                >`}
          </div>
        </div>
        ${this.renderChart(box)}
        ${this.layout === "phone" ? this.renderBandChips() : this.renderZoneRow(box, strings)}
        ${this.renderBandEditor(strings)}
      </section>
    `;
  }

  private renderChart(box: ChartBox): TemplateResult {
    const points = curvePoints(box, this.gains);
    const factoryPoints =
      this.factoryGains.length === 0 ? null : curvePoints(box, this.factoryGains);
    const zone = zoneOfBand(this.selectedBand);
    const edges = zoneEdges(box, zone);
    return html`
      <div class="chart-frame" style="height: ${box.height}px">
        <svg
          class="chart"
          width=${box.width}
          height=${box.height}
          viewBox="0 0 ${box.width} ${box.height}"
          aria-hidden="true"
        >
          <defs>
            <linearGradient id="area-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stop-color="var(--color-accent)" stop-opacity="0.22" />
              <stop offset="1" stop-color="var(--color-accent)" stop-opacity="0" />
            </linearGradient>
          </defs>
          <rect
            class="zone-highlight"
            x=${edges.left}
            y=${box.padY - 8}
            width=${edges.right - edges.left}
            height=${box.height - 2 * box.padY + 16}
            rx="6"
          />
          <path class="grid" d=${gridPath(box)} />
          <path class="zero" d=${zeroLinePath(box)} />
          <path class="area" d=${areaPath(box, points)} />
          ${factoryPoints === null
            ? nothing
            : svg`<path class="factory-curve" d=${smoothCurvePath(factoryPoints)} />`}
          <path class="curve" d=${smoothCurvePath(points)} />
          ${renderAxisLabels(box, this.layout)}
        </svg>
        ${this.layout === "phone"
          ? this.renderPlainDots(points)
          : this.renderBandButtons(points)}
      </div>
      ${this.layout === "phone" ? nothing : this.renderFrequencyLabels(box)}
    `;
  }

  /** On the phone the dots only report the curve. The chips below the
   * chart select a band instead. */
  private renderPlainDots(points: readonly { x: number; y: number }[]): TemplateResult {
    return html`
      ${points.map((point, band) => {
        const selected = band === this.selectedBand;
        const size = selected ? 16 : 9;
        return html`
          <span
            class="dot ${selected ? "selected" : this.isChanged(band) ? "changed" : ""}"
            style="left: ${point.x - size / 2}px; top: ${point.y - size / 2}px; width: ${size}px; height: ${size}px"
          ></span>
        `;
      })}
    `;
  }

  private renderBandButtons(points: readonly { x: number; y: number }[]): TemplateResult {
    const hitSize = this.layout === "tablet" ? 44 : 36;
    return html`
      ${points.map((point, band) => {
        const selected = band === this.selectedBand;
        const size = selected ? (this.layout === "tablet" ? 20 : 18) : this.layout === "tablet" ? 13 : 11;
        return html`
          <button
            type="button"
            class="band-hit"
            style="left: ${point.x - hitSize / 2}px; top: ${point.y - hitSize / 2}px; width: ${hitSize}px; height: ${hitSize}px"
            aria-label=${this.bandAriaLabel(band)}
            aria-pressed=${selected}
            @click=${() => this.selectBand(band)}
            @keydown=${(event: KeyboardEvent) => this.onBandKeydown(event, band)}
            @pointerdown=${(event: PointerEvent) => this.startDrag(event, band)}
            @pointermove=${(event: PointerEvent) => this.dragTo(event)}
            @pointerup=${(event: PointerEvent) => this.endDrag(event)}
            @pointercancel=${(event: PointerEvent) => this.endDrag(event)}
          >
            <span
              class="dot ${selected ? "selected" : this.isChanged(band) ? "changed" : ""}"
              style="width: ${size}px; height: ${size}px"
            ></span>
          </button>
        `;
      })}
    `;
  }

  private renderFrequencyLabels(box: ChartBox): TemplateResult {
    return html`
      <div class="frequency-labels" style="height: 18px">
        ${EQ_BAND_FREQUENCIES.map(
          (_frequency, band) => html`
            <span
              class="frequency ${band === this.selectedBand ? "selected" : ""}"
              style="left: ${bandX(box, band) - 24}px"
              >${shortFrequencyLabel(band)}</span
            >
          `,
        )}
      </div>
    `;
  }

  private renderZoneRow(box: ChartBox, strings: UiStrings): TemplateResult {
    const selectedZone = zoneOfBand(this.selectedBand);
    return html`
      <div class="zone-row">
        ${EQ_ZONES.map((zone) => {
          const edges = zoneEdges(box, zone);
          return html`
            <button
              type="button"
              class="zone ${zone.index === selectedZone.index ? "selected" : ""}"
              style="left: ${edges.left + 2}px; width: ${edges.right - edges.left - 4}px"
              aria-pressed=${zone.index === selectedZone.index}
              @click=${() => this.selectBand(zone.firstBand)}
            >
              ${zoneName(strings, zone)}
            </button>
          `;
        })}
      </div>
    `;
  }

  private renderBandChips(): TemplateResult {
    return html`
      <div class="chip-row">
        ${EQ_BAND_FREQUENCIES.map(
          (_frequency, band) => html`
            <button
              type="button"
              class="chip ${band === this.selectedBand
                ? "selected"
                : this.isChanged(band)
                  ? "changed"
                  : ""}"
              aria-label=${this.bandAriaLabel(band)}
              aria-pressed=${band === this.selectedBand}
              @click=${() => this.selectBand(band)}
              @keydown=${(event: KeyboardEvent) => this.onBandKeydown(event, band)}
            >
              <span class="chip-frequency">${shortFrequencyLabel(band)}</span>
              <span class="chip-gain">${formatGain(this.gainOf(band))}</span>
            </button>
          `,
        )}
      </div>
    `;
  }

  private renderBandEditor(strings: UiStrings): TemplateResult {
    const band = this.selectedBand;
    const zone = zoneOfBand(band);
    const factory = this.factoryGainOf(band);
    return html`
      <div class="band-editor">
        <div class="band-text">
          <div class="band-name-row">
            <span class="band-name">${fullFrequencyLabel(band)}</span>
            <span class="band-zone">${zoneName(strings, zone)}</span>
          </div>
          <p class="band-hint">${zoneHint(strings, zone)}</p>
          <input
            type="range"
            min=${MIN_GAIN_DB}
            max=${MAX_GAIN_DB}
            step=${GAIN_STEP_DB}
            .value=${String(this.gainOf(band))}
            aria-label=${strings.gainSliderLabel}
            @input=${(event: Event) =>
              this.changeGain(band, Number((event.target as HTMLInputElement).value))}
          />
        </div>
        <div class="band-controls">
          <div class="stepper">
            <button
              type="button"
              class="step"
              aria-label=${strings.lowerGainLabel}
              @click=${() => this.changeGain(band, this.gainOf(band) - GAIN_STEP_DB)}
            >
              −
            </button>
            <span class="gain-readout">${formatGain(this.gainOf(band))}</span>
            <button
              type="button"
              class="step"
              aria-label=${strings.raiseGainLabel}
              @click=${() => this.changeGain(band, this.gainOf(band) + GAIN_STEP_DB)}
            >
              +
            </button>
          </div>
          <div class="factory-row">
            <span class="factory-value"
              >${factory === null
                ? nothing
                : `${strings.factoryValuePrefix} ${formatGain(factory)} dB`}</span
            >
            ${this.isChanged(band)
              ? html`
                  <button
                    type="button"
                    class="reset-band"
                    @click=${() => this.changeGain(band, factory ?? 0)}
                  >
                    ${strings.resetBand}
                  </button>
                `
              : nothing}
          </div>
        </div>
      </div>
    `;
  }

  private bandAriaLabel(band: number): string {
    return `${fullFrequencyLabel(band)}, ${formatGain(this.gainOf(band))} dB`;
  }

  /** The left and right keys move the selection, and the up and down
   * keys change the gain of the selected band. */
  private onBandKeydown(event: KeyboardEvent, band: number): void {
    if (event.key === "ArrowLeft" && band > 0) {
      event.preventDefault();
      this.selectBand(band - 1);
      return;
    }
    if (event.key === "ArrowRight" && band < LAST_BAND) {
      event.preventDefault();
      this.selectBand(band + 1);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      this.changeGain(band, this.gainOf(band) + GAIN_STEP_DB);
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      this.changeGain(band, this.gainOf(band) - GAIN_STEP_DB);
    }
  }

  private selectBand(band: number): void {
    this.selectedBand = band;
  }

  /** Dragging a dot up and down sets the gain of its band. The editor
   * captures the pointer, so the drag continues outside the dot. */
  private startDrag(event: PointerEvent, band: number): void {
    this.selectedBand = band;
    this.draggingBand = band;
    (event.target as Element).setPointerCapture(event.pointerId);
  }

  private dragTo(event: PointerEvent): void {
    const band = this.draggingBand;
    if (band === null) {
      return;
    }
    const frame = this.shadowRoot?.querySelector(".chart-frame");
    if (frame === null || frame === undefined) {
      return;
    }
    event.preventDefault();
    const box = chartBox(this.layout, this.chartWidth);
    const offsetY = event.clientY - frame.getBoundingClientRect().top;
    this.changeGain(band, gainFromY(box, offsetY));
  }

  private endDrag(event: PointerEvent): void {
    if (this.draggingBand === null) {
      return;
    }
    this.draggingBand = null;
    const target = event.target as Element;
    if (target.hasPointerCapture(event.pointerId)) {
      target.releasePointerCapture(event.pointerId);
    }
  }

  private changeGain(band: number, gain: number): void {
    this.selectedBand = band;
    this.dispatchEvent(
      new CustomEvent("gain-change", { detail: { band, value: clampGain(gain) } }),
    );
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "eq-editor": EqEditor;
  }
}
