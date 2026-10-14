import { css } from "lit";

export const profileActivationStyles = css`
  :host {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px 12px;
  }
  button {
    height: 36px;
    padding: 0 16px;
    border-radius: var(--radius);
    font: inherit;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;

    &:disabled {
      opacity: 0.5;
      cursor: default;
    }
  }
  .activate {
    border: 0;
    background: var(--color-accent);
    color: var(--color-on-accent);
  }
  .apply {
    border: 1px solid var(--color-accent);
    background: transparent;
    color: var(--color-accent);
  }
  .status {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 4px 12px;
    border-radius: var(--radius-pill);
    background: var(--color-badge);
    color: var(--color-text-2);
    font-size: 13px;
    font-weight: 500;

    &.applied {
      background: color-mix(in srgb, var(--color-accent) 16%, transparent);
      color: var(--color-accent);
    }

    &.failed {
      background: var(--color-warn-bg);
      border: 1px solid var(--color-warn-border);
    }
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--color-outline);
    flex-shrink: 0;
  }
  .applied .dot {
    background: var(--color-accent);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-accent) 25%, transparent);
  }
  .outdated .dot {
    background: var(--color-accent);
  }
  .hint {
    font-size: 13px;
    color: var(--color-muted-foreground);
  }
`;
