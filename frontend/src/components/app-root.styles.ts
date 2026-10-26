import { css } from "lit";

/**
 * One shell, three layouts. Media queries switch between them:
 * phone below 700px, tablet from 700px, desktop from 1200px.
 * The `.drawer` is the permanent sidebar on desktop, a left drawer on
 * tablet, and a bottom sheet on the phone.
 */
export const appRootStyles = css`
  :host {
    display: flex;
    min-height: 100vh;
    min-height: 100dvh;
  }
  .content {
    flex-grow: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    position: relative;
  }
  header {
    height: 60px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 0 16px;
    border-bottom: 1px solid var(--color-divider);
  }
  .header-start {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    flex-grow: 1;
  }
  .header-controls {
    position: relative;
    display: flex;
    align-items: center;
    gap: 12px;
    min-width: 0;
  }
  .open-settings {
    display: grid;
    flex: none;
    place-items: center;
    width: 36px;
    height: 36px;
    padding: 0;
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-card);
    color: var(--color-muted-foreground);
    cursor: pointer;

    &:hover,
    &[aria-pressed="true"] {
      border-color: var(--color-border-strong);
      color: var(--color-accent);
    }
  }
  .header-divider {
    width: 1px;
    height: 24px;
    background: var(--color-divider);
  }
  .phone-profile-text {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    min-width: 0;
  }
  .phone-profile-title {
    font-family: var(--font-display);
    font-size: 18px;
    font-weight: 700;
    line-height: 1.1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  }
  .phone-profile-caption {
    font-size: 12px;
    color: var(--color-muted-foreground);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  }
  .profiles-toggle.phone {
    flex-grow: 1;
    min-width: 0;
    gap: 8px;
    padding: 0 10px;
    border: 0;
    background: transparent;
    color: var(--color-foreground);
    text-align: left;
  }
  /* The phone header has too little room for the name next to the
     controls, so it shows the mark alone. */
  .wordmark {
    display: flex;
    align-items: center;
    gap: 10px;

    .mark {
      color: var(--color-accent);
      flex-shrink: 0;
    }

    h1 {
      display: none;
    }
  }
  h1 {
    margin: 0;
    font-family: var(--font-display);
    font-size: 19px;
    font-weight: 700;
    letter-spacing: -0.01em;
    white-space: nowrap;
  }
  .profiles-toggle {
    display: flex;
    align-items: center;
    gap: 8px;
    height: 44px;
    padding: 0 12px;
    background: var(--color-card);
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    color: var(--color-foreground);
    font: inherit;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;

    &:hover {
      border-color: var(--color-accent);
      color: var(--color-accent);
    }
  }
  main {
    flex-grow: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 20px 16px 16px;
  }
  .heading-row {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 24px;
  }
  .heading-text {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
  }
  .breadcrumb {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 13px;
    color: var(--color-muted-foreground);
  }
  .profile-title {
    margin: 0;
    font-family: var(--font-display);
    font-size: 18px;
    font-weight: 700;
    line-height: 1;
    letter-spacing: -0.02em;
  }
  .badge {
    padding: 2px 8px;
    border-radius: var(--radius-pill);
    background: var(--color-badge);
    color: var(--color-text-2);
    font-size: 12px;
    font-weight: 500;
    white-space: nowrap;

    &.edited {
      background: color-mix(in srgb, var(--color-accent) 13%, transparent);
      color: var(--color-accent);
    }
  }
  .start-hint {
    font-size: 13px;
    color: var(--color-muted-foreground);
  }
  .heading-actions {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .heading-actions button,
  .save-bar button {
    height: 40px;
    padding: 0 16px;
    border-radius: var(--radius);
    font: inherit;
    font-size: 14px;
    cursor: pointer;
  }
  .heading-actions .secondary,
  .save-bar .secondary {
    border: 1px solid var(--color-border);
    background: transparent;
    color: var(--color-foreground);

    &:hover {
      border-color: var(--color-accent);
      color: var(--color-accent);
    }
  }
  .heading-actions .primary,
  .save-bar .primary {
    border: 0;
    padding: 0 18px;
    background: var(--color-accent);
    color: var(--color-on-accent);
    font-weight: 600;
  }
  .save-bar {
    position: sticky;
    bottom: 68px;
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
    padding: 10px 16px;
    background: var(--color-card);
    border-top: 1px solid var(--color-divider);

    .badge {
      flex-grow: 1;
    }
  }
  .panels {
    display: flex;
    flex-direction: column;
    gap: 16px;
    min-width: 0;
  }
  .page-switch {
    display: flex;
    gap: 4px;
    padding: 4px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    background: var(--color-card);

    button {
      height: 32px;
      padding: 0 16px;
      border: 0;
      border-radius: var(--radius);
      background: transparent;
      color: var(--color-muted-foreground);
      font: inherit;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;

      &[aria-pressed="true"] {
        background: var(--color-accent);
        color: var(--color-on-accent);
      }
    }
  }
  .car-line {
    display: flex;
    align-items: center;
    gap: 10px;
    align-self: flex-start;
    max-width: 100%;
    padding: 8px 14px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-pill);
    background: var(--color-card);
    color: var(--color-foreground);
    font: inherit;
    font-size: 14px;
    cursor: pointer;

    &:hover {
      border-color: var(--color-accent);
    }
  }
  .car-line-label {
    color: var(--color-muted-foreground);
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .car-line-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 600;
  }
  .area-correction {
    grid-area: correction;
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-width: 0;
  }
  .area-eq {
    grid-area: eq;
  }
  .area-speakers {
    grid-area: speakers;
  }
  .area-filters {
    grid-area: filters;
  }
  .area-style {
    grid-area: style;
    display: flex;
    flex-direction: column;
    gap: 16px;
    min-width: 0;
  }
  .area-audio {
    grid-area: audio;
  }
  .empty {
    color: var(--color-muted-foreground);
  }
  .hint {
    font-size: 13px;
    color: var(--color-muted-foreground);
    margin: 0;
  }
  .drawer-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(8, 7, 6, 0.7);
    z-index: 40;
  }
  .drawer {
    position: fixed;
    inset-inline: 0;
    bottom: 0;
    max-height: 75vh;
    background: var(--color-sidebar);
    border-top: 1px solid var(--color-divider);
    border-radius: 20px 20px 0 0;
    padding: 8px 16px 16px;
    overflow-y: auto;
    z-index: 50;
    transform: translateY(100%);
    transition: transform 0.2s ease;

    &.open {
      transform: translateY(0);
    }
  }
  .grab-handle {
    width: 40px;
    height: 4px;
    margin: 0 auto 8px;
    border-radius: var(--radius-pill);
    background: var(--color-border-strong);
  }
  .drawer-header {
    display: flex;
    justify-content: flex-end;
  }
  .drawer-close {
    background: none;
    border: none;
    color: var(--color-muted-foreground);
    font-size: 20px;
    line-height: 1;
    padding: 8px;
    cursor: pointer;

    &:hover {
      color: var(--color-foreground);
    }
  }
  .sidebar-wordmark {
    display: none;
  }
  .tab-bar {
    position: sticky;
    bottom: 0;
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    height: 68px;
    flex-shrink: 0;
    background: var(--color-sidebar);
    border-top: 1px solid var(--color-divider);
  }
  .tab {
    display: flex;
    align-items: center;
    justify-content: center;
    background: none;
    border: 0;
    color: var(--color-text-2);
    font: inherit;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;

    &[aria-pressed="true"] {
      color: var(--color-accent);
    }
  }

  @media (min-width: 700px) {
    header {
      height: 68px;
      padding: 0 32px;
    }
    .wordmark h1 {
      display: block;
    }
    main {
      gap: 20px;
      padding: 24px 32px 32px;
    }
    .profile-title {
      font-size: 40px;
    }
    .drawer {
      inset-block: 0;
      inset-inline-start: 0;
      inset-inline-end: auto;
      width: 340px;
      max-height: none;
      border-top: 0;
      border-right: 1px solid var(--color-divider);
      border-radius: 0;
      padding: 16px;
      transform: translateX(-100%);

      &.open {
        transform: translateX(0);
      }
    }
    .grab-handle {
      display: none;
    }
    .tab-bar {
      display: none;
    }
    .panels {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      grid-template-areas:
        "audio audio"
        "eq eq"
        "style style";
      gap: 20px;
      align-items: start;
    }
    .panels.car {
      grid-template-areas:
        "speakers speakers"
        "correction correction"
        "filters filters";
    }
  }

  @media (min-width: 1200px) {
    header {
      height: 64px;
      justify-content: flex-end;
      padding: 0 40px;
    }
    .header-start {
      display: none;
    }
    main {
      gap: 24px;
      padding: 28px 40px 40px;
    }
    .profile-title {
      font-size: 44px;
    }
    .drawer-backdrop {
      display: none;
    }
    .drawer {
      position: static;
      width: 288px;
      flex-shrink: 0;
      display: flex;
      flex-direction: column;
      gap: 24px;
      padding: 20px 16px;
      transform: none;
      background: var(--color-sidebar);
    }
    .drawer-header {
      display: none;
    }
    .sidebar-wordmark {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 4px 8px 8px;

      .mark {
        color: var(--color-accent);
        flex-shrink: 0;
      }
    }
    .panels {
      grid-template-columns: minmax(0, 1fr) 360px;
      grid-template-areas:
        "audio audio"
        "eq eq"
        "style style";
      gap: 24px;
    }
    .panels.car {
      grid-template-columns: 360px minmax(0, 1fr);
      grid-template-areas:
        "speakers correction"
        "filters correction";
    }
  }
`;
