import { css } from "lit";

export const systemDialogStyles = css`
  :host {
    display: contents;
  }
  dialog {
    width: min(520px, calc(100vw - 32px));
    max-height: calc(100dvh - 32px);
    padding: 20px;
    box-sizing: border-box;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-background);
    color: var(--color-foreground);

    &::backdrop {
      background: rgb(0 0 0 / 0.6);
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
  }
  h2 {
    margin: 0;
    font-family: var(--font-display);
    font-size: 18px;
  }
  h3 {
    margin: 0 0 8px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--color-muted-foreground);
  }
  section {
    margin-top: 18px;
    padding-top: 14px;
    border-top: 1px solid var(--color-divider);

    &:first-of-type {
      border-top: 0;
      padding-top: 0;
    }
  }
  dl {
    display: grid;
    grid-template-columns: max-content minmax(0, 1fr);
    gap: 4px 16px;
    margin: 0;
    font-size: 13px;
  }
  dt {
    color: var(--color-text-2);
  }
  dd {
    margin: 0;
    font-family: var(--font-mono);
    font-size: 12px;
    white-space: pre-line;
    overflow-wrap: anywhere;
  }
  .network dt {
    font-family: var(--font-mono);
    font-size: 12px;
  }
  .state {
    margin-left: 4px;
    color: var(--color-muted-foreground);
  }
  .usage {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 4px 16px;
    margin-bottom: 10px;
    font-size: 13px;
  }
  .usage-label {
    color: var(--color-text-2);
  }
  .usage-value {
    justify-self: end;
    font-family: var(--font-mono);
    font-size: 12px;
  }
  meter {
    grid-column: 1 / -1;
    width: 100%;
    height: 6px;
    appearance: none;
    border-radius: var(--radius-pill);
    background: var(--color-inset);
    overflow: hidden;

    &::-webkit-meter-bar {
      height: 6px;
      border: 0;
      border-radius: var(--radius-pill);
      background: var(--color-inset);
    }
    &::-webkit-meter-optimum-value,
    &::-webkit-meter-suboptimum-value,
    &::-webkit-meter-even-less-good-value {
      background: var(--color-accent);
    }
    &::-moz-meter-bar {
      background: var(--color-accent);
    }
  }
  .freshness {
    padding: 1px 8px;
    border-radius: var(--radius-pill);
    background: var(--color-badge);
    color: var(--color-text-2);

    &[data-freshness="live"] {
      background: var(--color-accent);
      color: var(--color-on-accent);
    }
    &[data-freshness="outdated"] {
      background: var(--color-warn-bg);
      border: 1px solid var(--color-warn-border);
    }
  }
  .hint {
    margin: 10px 0 0;
    font-size: 13px;
    color: var(--color-muted-foreground);
  }
  button {
    height: 32px;
    padding: 0 12px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-card);
    color: var(--color-foreground);
    font: inherit;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;

    &:hover {
      border-color: var(--color-border-strong);
    }
  }
  .close {
    width: 36px;
    padding: 0;
    border: 0;
    background: transparent;
    font-size: 20px;
  }
  .reload {
    margin-left: 8px;
  }
`;
