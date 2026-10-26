import { css } from "lit";

export const displaySettingsStyles = css`
  :host {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .hint {
    margin: 0;
    font-size: 13px;
    line-height: 1.45;
    color: var(--color-muted-foreground);
  }
  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .row-label {
    font-size: 14px;
    font-weight: 600;
  }
  select {
    height: 40px;
    min-width: 11rem;
    padding: 0 10px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-card);
    color: var(--color-foreground);
    font: inherit;
    font-size: 15px;
  }
`;
