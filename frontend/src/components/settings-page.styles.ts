import { css } from "lit";

export const settingsPageStyles = css`
  :host {
    display: grid;
    grid-template-columns: 200px minmax(0, 720px);
    gap: 24px;
    align-items: start;
    color: var(--color-foreground);

    @media (max-width: 720px) {
      grid-template-columns: minmax(0, 1fr);
      gap: 12px;
    }
  }
  .sections {
    display: flex;
    flex-direction: column;
    gap: 4px;

    @media (max-width: 720px) {
      flex-direction: row;
      overflow-x: auto;
    }

    button {
      height: 40px;
      padding: 0 14px;
      border: 1px solid transparent;
      border-radius: var(--radius);
      background: transparent;
      color: var(--color-muted-foreground);
      font: inherit;
      font-size: 14px;
      font-weight: 600;
      text-align: left;
      white-space: nowrap;
      cursor: pointer;

      &:hover {
        color: var(--color-foreground);
      }
      &[aria-pressed="true"] {
        border-color: var(--color-border);
        background: var(--color-card);
        color: var(--color-accent);
      }
    }
  }
  .card {
    padding: 20px;
    border: 1px solid var(--color-divider);
    border-radius: var(--radius-lg);
    background: var(--color-card);

    @media (max-width: 720px) {
      padding: 16px;
    }
  }
  h2 {
    margin: 0 0 16px;
    font-family: var(--font-display);
    font-size: 18px;
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }
  .hint {
    font-size: 13px;
    color: var(--color-muted-foreground);
  }
`;
