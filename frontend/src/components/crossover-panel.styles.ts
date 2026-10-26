import { css } from "lit";

export const crossoverPanelStyles = css`
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
    flex-direction: column;
    gap: 4px;
  }
  h2 {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
  }
  .caption,
  .hint {
    margin: 0;
    font-size: 13px;
    line-height: 1.45;
    color: var(--color-muted-foreground);
  }
  .speaker-mode {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;
    color: var(--color-muted-foreground);

    & select {
      height: 44px;
      padding: 0 12px;
      border: 1px solid var(--color-border);
      border-radius: var(--radius);
      background: var(--color-inset);
      color: var(--color-foreground);
      font: inherit;
      font-size: 15px;
    }
  }
  .filters {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .filter {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px 16px;
    padding: 12px 0;
    border-top: 1px solid var(--color-divider);

    &:first-child {
      border-top: none;
      padding-top: 0;
    }
  }
  .filter-name {
    display: flex;
    flex-direction: column;
    gap: 2px;

    & .speaker {
      font-size: 14px;
      font-weight: 600;
    }
    & .kind {
      font-size: 12px;
      color: var(--color-muted-foreground);
    }
  }
  .value {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 2px;
    font-size: 14px;

    & .setting {
      font-family: var(--font-mono);
    }
    & .hint {
      font-size: 12px;
    }
  }
  .editor {
    display: flex;
    gap: 12px;

    & label {
      display: flex;
      flex-direction: column;
      gap: 4px;
      font-size: 12px;
      color: var(--color-muted-foreground);
    }
    & select {
      height: 44px;
      padding: 0 12px;
      border: 1px solid var(--color-border);
      border-radius: var(--radius);
      background: var(--color-inset);
      color: var(--color-foreground);
      font: inherit;
      font-size: 15px;
    }
  }
  .message {
    margin: 0;
    font-size: 13px;
    color: var(--color-text-2);
  }
`;
