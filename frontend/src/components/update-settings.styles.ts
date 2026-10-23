import { css } from "lit";

export const updateSettingsStyles = css`
  :host {
    display: block;
    color: var(--color-foreground);
  }
  .intro,
  .hint {
    margin: 0;
    font-size: 13px;
    color: var(--color-muted-foreground);
  }
  .versions {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 8px 16px;
    margin: 16px 0;
    font-size: 14px;

    dt {
      color: var(--color-text-2);
    }
    dd {
      margin: 0;
      overflow-wrap: anywhere;
    }
    a {
      margin-left: 8px;
      color: var(--color-reference);
    }
  }
  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 14px 0;
    border-top: 1px solid var(--color-divider);
    border-bottom: 1px solid var(--color-divider);
    cursor: pointer;
  }
  .row-text {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .row-label {
    font-size: 14px;
    font-weight: 600;
  }
  /* A switch, as Fluidd draws its own settings: a track and a knob. */
  input[type="checkbox"] {
    position: relative;
    flex: none;
    width: 42px;
    height: 24px;
    margin: 0;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-pill);
    background: var(--color-inset);
    appearance: none;
    cursor: pointer;
    transition: background 120ms;

    &::after {
      content: "";
      position: absolute;
      top: 2px;
      left: 2px;
      width: 18px;
      height: 18px;
      border-radius: 50%;
      background: var(--color-muted-foreground);
      transition: transform 120ms;
    }
    &:checked {
      border-color: var(--color-accent);
      background: var(--color-accent);

      &::after {
        background: var(--color-on-accent);
        transform: translateX(18px);
      }
    }
    &:focus-visible {
      outline: 2px solid var(--color-accent);
      outline-offset: 2px;
    }
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
    margin-top: 16px;
  }
  button {
    height: 36px;
    padding: 0 14px;
    border: 1px solid var(--color-accent);
    border-radius: var(--radius);
    background: var(--color-accent);
    color: var(--color-on-accent);
    font: inherit;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;

    &:disabled {
      opacity: 0.5;
      cursor: default;
    }
  }
  .message {
    margin: 0;
    font-size: 13px;
    color: var(--color-text-2);
  }
  h3 {
    margin: 20px 0 8px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--color-text-2);
  }
  .history {
    margin: 0;
    padding: 0;
    list-style: none;
    font-size: 14px;

    li {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 6px 0;
      border-bottom: 1px solid var(--color-divider);
    }
  }
`;
