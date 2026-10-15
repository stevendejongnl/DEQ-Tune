import { css } from "lit";

export const devicePillStyles = css`
  :host {
    display: flex;
    align-items: center;
    gap: 8px;
    height: 40px;
    padding: 0 14px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-pill);
    background: var(--color-card);
  }
  .dot {
    width: 8px;
    height: 8px;
    flex-shrink: 0;
    border-radius: 50%;
    background: var(--color-outline);

    :host([linkstate="connected"]) & {
      background: var(--color-accent);
    }
  }
  .device-label {
    font-size: 13px;
    color: var(--color-text-2);
    white-space: nowrap;
  }
  .freshness {
    font-family: var(--font-mono);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--color-muted-foreground);

    :host([linkstate="no-bridge"]) & {
      color: var(--color-accent);
    }
  }
  .firmware {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--color-muted-foreground);
  }
`;
