import { css } from "lit";

/** The Undo button above an EQ curve. The main EQ and the car profile's
 * correction curve share it, so both look the same. */
export const undoButtonStyles = css`
  .undo-row {
    display: flex;
    justify-content: flex-end;
  }
  .undo {
    height: 36px;
    padding: 0 14px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: transparent;
    color: var(--color-foreground);
    font: inherit;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;

    &:disabled {
      opacity: 0.4;
      cursor: default;
    }
  }
`;
