import { css } from "lit";

export const audioControlsStyles = css`
  :host {
    display: block;
  }
  .panel {
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    gap: 20px;
    padding: 16px;
    border: 1px solid var(--color-divider);
    border-radius: var(--radius-lg);
    background: var(--color-card);
  }
  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  h2 {
    margin: 0;
    font-size: 1rem;
  }
  .unread {
    margin: 0;
    opacity: 0.7;
  }
  .label {
    font-size: 13px;
    color: var(--color-muted-foreground);
  }
  .volume {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 16px;
    border: 1px solid var(--color-divider);
    border-radius: var(--radius-md);
    background: var(--color-inset);
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
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-md);
    background: var(--color-card);
    color: var(--color-foreground);
    font: inherit;
    font-size: 20px;
    cursor: pointer;

    &:hover:not(:disabled) {
      border-color: var(--color-accent);
      color: var(--color-accent);
    }
    &:disabled {
      opacity: 0.4;
      cursor: default;
    }
  }
  .volume-readout {
    flex-grow: 1;
    text-align: center;
    font-family: var(--font-mono);
    font-size: 30px;
    font-weight: 500;
    font-variant-numeric: tabular-nums;

    .unit {
      font-size: 16px;
      color: var(--color-muted-foreground);
    }
  }
  /* The track fills with the accent up to the thumb. The fill comes from
     the --fill custom property, which the template sets. */
  input[type="range"] {
    --track: 6px;
    --thumb: 24px;
    width: 100%;
    height: var(--thumb);
    margin: 0;
    background: transparent;
    appearance: none;
    /* A vertical swipe over the slider scrolls the page. */
    touch-action: pan-y;
    cursor: pointer;

    &::-webkit-slider-runnable-track {
      height: var(--track);
      border-radius: var(--radius-pill);
      background: linear-gradient(
        to right,
        var(--color-accent) var(--fill, 0%),
        var(--color-border-strong) var(--fill, 0%)
      );
    }
    &::-webkit-slider-thumb {
      width: var(--thumb);
      height: var(--thumb);
      margin-top: calc((var(--track) - var(--thumb)) / 2);
      border: 3px solid var(--color-card);
      border-radius: 50%;
      background: var(--color-accent);
      box-shadow: 0 0 0 1px var(--color-accent);
      appearance: none;
    }
    &::-moz-range-track {
      height: var(--track);
      border-radius: var(--radius-pill);
      background: var(--color-border-strong);
    }
    &::-moz-range-progress {
      height: var(--track);
      border-radius: var(--radius-pill);
      background: var(--color-accent);
    }
    &::-moz-range-thumb {
      width: var(--thumb);
      height: var(--thumb);
      border: 3px solid var(--color-card);
      border-radius: 50%;
      background: var(--color-accent);
    }
    &:focus-visible {
      outline: 2px solid var(--color-accent);
      outline-offset: 4px;
      border-radius: var(--radius-pill);
    }
    &:disabled {
      opacity: 0.4;
      cursor: default;
    }
  }
  .source {
    display: flex;
    flex-direction: column;
    gap: 6px;

    select {
      height: 44px;
      padding: 0 12px;
      border: 1px solid var(--color-border);
      border-radius: var(--radius);
      background: var(--color-inset);
      color: var(--color-foreground);
      font: inherit;
      font-size: 15px;

      &:disabled {
        opacity: 0.5;
      }
    }
  }
  .readout {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 6px 16px;
    margin: 0;
    font-size: 14px;
  }
  dt {
    color: var(--color-muted-foreground);
  }
  dd {
    margin: 0;
    font-variant-numeric: tabular-nums;
  }
  /* A muted unit is the thing most likely to explain silence, so it is
     the one readout that draws the eye rather than sitting in the list. */
  dd.warn {
    color: var(--color-warning, #c77);
    font-weight: 600;
  }
`;
