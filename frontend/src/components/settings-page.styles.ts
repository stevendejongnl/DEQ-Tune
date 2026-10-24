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
      scroll-behavior: smooth;
      scroll-snap-type: x proximity;
      scroll-padding-inline: 16px;
      overscroll-behavior-x: contain;
      scrollbar-width: none;
      /* The edges fade, so a cut-off section reads as "more this way". */
      mask-image: linear-gradient(to right, transparent, black 16px, black calc(100% - 16px), transparent);

      &::-webkit-scrollbar {
        display: none;
      }
      button {
        scroll-snap-align: start;
        flex-shrink: 0;
      }
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
  .android-language {
    margin: 12px 0 0;
  }
  .translations {
    margin-top: 20px;
    padding-top: 16px;
    border-top: 1px solid var(--color-divider);

    h3 {
      margin: 0 0 6px;
      font-size: 14px;
      color: var(--color-text-2);
    }
    p {
      margin: 0;
    }
  }
  .links {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 12px 0 0;
    padding: 0;
    list-style: none;
    font-size: 14px;

    a {
      color: var(--color-accent);
    }
  }
`;
