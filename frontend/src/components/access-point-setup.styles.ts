import { css } from "lit";

export const accessPointSetupStyles = css`
  :host {
    position: fixed;
    inset: 0;
    z-index: 400;
    display: grid;
    place-items: center;
    background: rgb(0 0 0 / 0.6);
  }
  /* The page's reset clears padding on the host, so the card keeps its own
     gutter. */
  .card {
    box-sizing: border-box;
    width: min(420px, calc(100% - 32px));
    max-height: calc(100% - 32px);
    overflow-y: auto;
    padding: 18px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-lg);
    background: var(--color-card);
    color: var(--color-foreground);
    box-shadow: 0 8px 24px rgb(0 0 0 / 0.45);
  }
  h2 {
    margin: 0;
    font-size: 17px;
    font-weight: 800;
  }
  p {
    margin: 8px 0 0;
    font-size: 14px;
    line-height: 1.45;
    color: var(--color-text-2);
  }
  access-point-key-form {
    margin-top: 14px;
  }
  .footer {
    display: flex;
    justify-content: flex-end;
    margin-top: 12px;
  }
  button {
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
  }
`;
