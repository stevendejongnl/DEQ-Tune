import { css } from "lit";

export const eqEditorStyles = css`
  :host {
    display: block;
  }
  .panel {
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 16px;
    border: 1px solid var(--color-divider);
    border-radius: var(--radius-lg);
    background: var(--color-card);
  }
  .panel-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
  }
  h2 {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
  }
  .legend {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 12px;
    color: var(--color-muted-foreground);

    .legend-entry {
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .swatch {
      width: 14px;

      &.yours {
        height: 2px;
        background: var(--color-accent);
      }

      &.factory {
        height: 0;
        border-top: 2px dashed var(--color-reference);
      }
    }
  }
  .chart-frame {
    position: relative;
    width: 100%;
  }
  .chart {
    position: absolute;
    left: 0;
    top: 0;
  }
  .zone-highlight {
    fill: var(--color-foreground);
    fill-opacity: 0.035;
  }
  .grid {
    stroke: var(--color-grid);
    stroke-width: 1;
    fill: none;
  }
  .zero {
    stroke: var(--color-zero);
    stroke-width: 1;
    fill: none;
  }
  .area {
    fill: url(#area-fill);
  }
  .factory-curve {
    stroke: var(--color-reference);
    stroke-width: 1.5;
    stroke-dasharray: 4 4;
    opacity: 0.8;
    fill: none;
  }
  .curve {
    stroke: var(--color-accent);
    stroke-width: 2.5;
    stroke-linecap: round;
    fill: none;
  }
  .axis-label {
    fill: var(--color-muted-foreground);
    font-family: var(--font-mono);
    font-size: 10px;
  }
  .band-hit {
    position: absolute;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    border: 0;
    border-radius: 50%;
    background: transparent;
    cursor: grab;
    /* The drag reads the pointer itself, so the browser must not pan
       or scroll the page instead. */
    touch-action: none;

    &:active {
      cursor: grabbing;
    }
  }
  .dot {
    position: absolute;
    box-sizing: border-box;
    border-radius: 50%;
    background: var(--color-background);
    border: 2px solid var(--color-text-2);

    &.changed {
      border-color: var(--color-accent);
    }

    &.selected {
      background: var(--color-accent);
      border: 0;
      box-shadow: 0 0 0 6px color-mix(in srgb, var(--color-accent) 20%, transparent);
    }
  }
  .band-hit .dot {
    position: static;
  }
  .frequency-labels {
    position: relative;
    width: 100%;
  }
  .frequency {
    position: absolute;
    top: 0;
    width: 48px;
    text-align: center;
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--color-muted-foreground);

    &.selected {
      color: var(--color-accent);
    }
  }
  .zone-row {
    position: relative;
    width: 100%;
    height: 30px;
  }
  .zone {
    position: absolute;
    top: 0;
    height: 30px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--color-border);
    background: transparent;
    color: var(--color-muted-foreground);
    font: inherit;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;

    &.selected {
      border-color: color-mix(in srgb, var(--color-accent) 40%, transparent);
      background: color-mix(in srgb, var(--color-accent) 12%, transparent);
      color: var(--color-accent);
    }
  }
  .chip-row {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    margin: 0 -16px;
    padding: 0 16px;
    scrollbar-width: none;

    &::-webkit-scrollbar {
      display: none;
    }
  }
  .chip {
    flex-shrink: 0;
    width: 60px;
    height: 56px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border);
    background: var(--color-card);
    color: var(--color-text-2);
    font: inherit;
    cursor: pointer;

    .chip-frequency {
      font-family: var(--font-mono);
      font-size: 11px;
      opacity: 0.8;
    }

    .chip-gain {
      font-family: var(--font-mono);
      font-size: 13px;
      font-weight: 500;
    }

    &.changed {
      color: var(--color-accent);
      border-color: color-mix(in srgb, var(--color-accent) 40%, transparent);
    }

    &.selected {
      background: var(--color-accent);
      border-color: var(--color-accent);
      color: var(--color-on-accent);
    }
  }
  .band-editor {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 16px;
    border-radius: var(--radius-md);
    background: var(--color-inset);
    border: 1px solid var(--color-border);
  }
  .band-text {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }
  .band-name-row {
    display: flex;
    align-items: baseline;
    gap: 10px;
  }
  .band-name {
    font-family: var(--font-mono);
    font-size: 18px;
    font-weight: 500;
  }
  .band-zone {
    font-size: 13px;
    font-weight: 600;
    color: var(--color-accent);
  }
  .band-hint {
    margin: 0;
    font-size: 13px;
    line-height: 1.45;
    color: var(--color-muted-foreground);
  }
  /* global.css cannot reach into this shadow tree, so this stylesheet
     sets the accent colour again. */
  input[type="range"] {
    width: 100%;
    margin-top: 8px;
    accent-color: var(--color-accent);
  }
  .band-controls {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .stepper {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .step {
    width: 48px;
    height: 48px;
    flex-shrink: 0;
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border-strong);
    background: var(--color-inset);
    color: var(--color-foreground);
    font: inherit;
    font-size: 20px;
    cursor: pointer;

    &:hover {
      border-color: var(--color-accent);
      color: var(--color-accent);
    }
  }
  .gain-readout {
    flex-grow: 1;
    text-align: center;
    font-family: var(--font-mono);
    font-size: 30px;
    font-weight: 500;
  }
  .factory-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    font-size: 12px;
    color: var(--color-muted-foreground);
  }
  .factory-value {
    font-family: var(--font-mono);
  }
  .reset-band {
    min-height: 32px;
    border: 0;
    background: transparent;
    color: var(--color-reference);
    font: inherit;
    font-size: 13px;
    text-decoration: underline;
    cursor: pointer;
  }

  @media (min-width: 700px) {
    .axis-label {
      font-size: 11px;
    }
    .panel {
      gap: 16px;
      padding: 20px 24px 24px;
    }
    .band-editor {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 24px;
      align-items: center;
      padding: 16px 18px;
    }
    .band-name {
      font-size: 20px;
    }
    .band-controls {
      align-items: flex-end;
    }
    .stepper {
      gap: 6px;
    }
    .step {
      width: 40px;
      height: 40px;
      border-radius: var(--radius);
      font-size: 18px;
    }
    .gain-readout {
      min-width: 96px;
      flex-grow: 0;
      font-size: 28px;
    }
    .zone {
      height: 36px;
    }
    .zone-row {
      height: 36px;
    }
  }

  @media (min-width: 1200px) {
    .zone,
    .zone-row {
      height: 30px;
    }
  }
`;
