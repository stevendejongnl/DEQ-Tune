import { css } from "lit";

export const notificationDockStyles = css`
  /* The container never takes a click meant for the page behind it. Only
     each card opts back in. */
  :host {
    position: fixed;
    left: 12px;
    bottom: 12px;
    z-index: 300;
    display: flex;
    flex-direction: column-reverse;
    gap: 8px;
    width: 320px;
    max-width: calc(100vw - 24px);
    pointer-events: none;

    /* The phone's tab bar sits at the bottom, so the dock sits above it. */
    @media (max-width: 720px) {
      left: 8px;
      right: 8px;
      bottom: calc(76px + env(safe-area-inset-bottom));
      width: auto;
    }
  }
  .card {
    pointer-events: auto;
    overflow: hidden;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-lg);
    background: var(--color-card);
    color: var(--color-foreground);
    box-shadow: 0 8px 24px rgb(0 0 0 / 0.45);
  }
  .hero {
    padding: 12px 14px 10px;
    background: var(--color-accent);
    color: var(--color-on-accent);
  }
  .badge {
    display: inline-block;
    margin-bottom: 6px;
    padding: 1px 6px;
    border-radius: 5px;
    background: rgb(0 0 0 / 0.15);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.06em;
  }
  .headline {
    margin: 0;
    font-size: 14px;
    font-weight: 800;
    line-height: 1.3;
  }
  .available .headline {
    padding: 12px 14px 0;
  }
  .highlight {
    margin: 4px 0 0;
    font-size: 12px;
    line-height: 1.45;
  }
  .footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 10px 14px 12px;
  }
  a {
    font-size: 13px;
    color: var(--color-reference);
  }
  button {
    height: 32px;
    padding: 0 12px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: transparent;
    color: var(--color-foreground);
    font: inherit;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
  }
  .primary {
    border-color: var(--color-accent);
    background: var(--color-accent);
    color: var(--color-on-accent);
  }
`;
