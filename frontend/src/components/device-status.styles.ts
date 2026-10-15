import { css } from "lit";

export const deviceStatusStyles = css`
  :host {
    display: block;
  }
  .open-system {
    display: block;
    padding: 0;
    border: 0;
    border-radius: var(--radius-pill);
    background: none;
    color: inherit;
    font: inherit;
    cursor: pointer;

    &:hover device-pill {
      border-color: var(--color-border-strong);
    }
  }
`;
