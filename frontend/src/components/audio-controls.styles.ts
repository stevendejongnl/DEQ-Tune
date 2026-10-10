import { css } from "lit";

export const audioControlsStyles = css`
  :host {
    display: block;
  }
  .panel {
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    gap: 16px;
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
  .refresh {
    padding: 4px 10px;
    border: 1px solid var(--color-divider);
    border-radius: var(--radius-sm);
    background: transparent;
    color: inherit;
    cursor: pointer;
  }
  .refresh[disabled] {
    opacity: 0.5;
    cursor: default;
  }
  .unread {
    margin: 0;
    opacity: 0.7;
  }
  .readout {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 4px 12px;
    margin: 0;
  }
  dt {
    opacity: 0.7;
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
  .control {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .control span {
    min-width: 7ch;
    opacity: 0.7;
  }
  .control input[type="range"] {
    flex: 1;
  }
`;
