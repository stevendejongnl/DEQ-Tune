import { css } from "lit";

export const equalizerEditorStyles = css`
  :host {
    display: block;
  }
  .panel {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .head {
    display: flex;
    flex-wrap: wrap;
    align-items: end;
    justify-content: space-between;
    gap: 12px;
  }
  .name {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
    flex: 1 1 220px;
    font-size: 12px;
    color: var(--color-muted-foreground);

    input {
      height: 40px;
      padding: 0 12px;
      border: 1px solid var(--color-border);
      border-radius: var(--radius);
      background: var(--color-sidebar);
      color: var(--color-foreground);
      font: inherit;
      font-size: 15px;
    }
  }
  .actions {
    display: flex;
    gap: 8px;

    button {
      height: 40px;
      padding: 0 16px;
      border-radius: var(--radius);
      font: inherit;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
    }
  }
  .delete {
    border: 1px solid var(--color-border);
    background: transparent;
    color: var(--color-foreground);

    &:hover {
      border-color: var(--color-warn-border);
    }
  }
  .done {
    border: 0;
    background: var(--color-accent);
    color: var(--color-on-accent);
  }
`;
