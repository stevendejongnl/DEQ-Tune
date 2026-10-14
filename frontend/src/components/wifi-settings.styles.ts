import { css } from "lit";

export const wifiSettingsStyles = css`
  :host {
    display: block;
  }
  button {
    height: 36px;
    padding: 0 14px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-card);
    color: var(--color-foreground);
    font: inherit;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;

    &:hover:not(:disabled) {
      border-color: var(--color-border-strong);
    }
    &:disabled {
      opacity: 0.5;
      cursor: default;
    }
  }
  .open {
    display: grid;
    place-items: center;
    width: 36px;
    padding: 0;
    color: var(--color-muted-foreground);

    &:hover {
      color: var(--color-foreground);
    }
  }
  dialog {
    width: min(440px, calc(100vw - 32px));
    max-height: calc(100dvh - 32px);
    padding: 20px;
    box-sizing: border-box;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-background);
    color: var(--color-foreground);

    &::backdrop {
      background: rgb(0 0 0 / 0.6);
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
  }
  h2 {
    margin: 0;
    font-family: var(--font-display);
    font-size: 18px;
  }
  h3 {
    margin: 0;
    font-size: 14px;
    color: var(--color-text-2);
  }
  .close {
    width: 36px;
    padding: 0;
    border: 0;
    background: transparent;
    font-size: 20px;
  }
  .intro,
  .empty,
  .hint {
    margin: 8px 0 0;
    font-size: 13px;
    color: var(--color-muted-foreground);
  }
  section,
  form {
    margin-top: 20px;
  }
  .section-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .saved {
    margin: 8px 0 0;
    padding: 0;
    list-style: none;

    li {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 0;
      border-bottom: 1px solid var(--color-divider);
    }
  }
  .ssid {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .tag {
    padding: 2px 8px;
    border-radius: var(--radius-pill);
    background: var(--color-badge);
    font-size: 12px;
    color: var(--color-text-2);

    &.connected {
      background: var(--color-accent);
      color: var(--color-on-accent);
    }
  }
  form {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  label {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 13px;
    color: var(--color-text-2);
  }
  input {
    height: 40px;
    padding: 0 10px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-card);
    color: var(--color-foreground);
    font: inherit;
    font-size: 15px;
  }
  .save {
    align-self: flex-end;
    border-color: var(--color-accent);
    background: var(--color-accent);
    color: var(--color-on-accent);
  }
  .message {
    margin: 16px 0 0;
    font-size: 13px;
    color: var(--color-text-2);
  }
`;
