import { css } from "lit";

export const profileListStyles = css`
  :host {
    display: flex;
    flex-direction: column;
    gap: 14px;
    min-height: 0;
  }
  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
  }
  .search {
    display: flex;
    align-items: center;
    gap: 8px;
    height: 44px;
    padding: 0 12px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    background: var(--color-sidebar);
    color: var(--color-muted-foreground);
    font-size: 14px;

    input {
      flex-grow: 1;
      min-width: 0;
      background: transparent;
      border: 0;
      color: var(--color-foreground);
      font: inherit;
      outline: none;

      &::-webkit-search-cancel-button {
        filter: grayscale(1);
      }
    }
  }
  .open-library,
  .library-back {
    align-self: flex-start;
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: transparent;
    color: var(--color-foreground);
    font: inherit;
    font-size: 13px;
    font-weight: 500;
    padding: 6px 12px;
    cursor: pointer;

    &:hover {
      border-color: var(--color-accent);
      color: var(--color-accent);
    }
  }
  .library-head {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .library-title {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
  }
  .group {
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-height: 0;
  }
  .group-head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 4px 8px;
  }
  .head-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .head-action {
    white-space: nowrap;
    border: 0;
    background: transparent;
    color: var(--color-accent);
    font: inherit;
    font-size: 12px;
    font-weight: 600;
    padding: 4px 8px;
    border-radius: var(--radius-sm);
    cursor: pointer;

    &:hover {
      background: color-mix(in srgb, var(--color-accent) 12%, transparent);
    }
  }
  .custom-row.renaming {
    padding: 4px;
  }
  .rename-input {
    width: 100%;
    height: 36px;
    padding: 0 8px;
    border: 1px solid var(--color-accent);
    border-radius: var(--radius-sm);
    background: var(--color-inset);
    color: var(--color-foreground);
    font: inherit;
    font-size: 14px;
    outline: none;
  }
  .group-label {
    white-space: nowrap;
    margin: 0;
    padding: 0 8px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--color-muted-foreground);
  }
  .empty {
    margin: 0;
    padding: 0 8px;
    font-size: 13px;
    color: var(--color-muted-foreground);
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
  }
  .custom-list {
    gap: 8px;
  }
  .custom-row {
    position: relative;
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 0 4px 0 0;
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-card);

    &.selected {
      background: var(--color-inset);
      border-color: var(--color-accent);
    }
  }
  .name {
    flex-grow: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
    padding: 10px 12px;
    border: 0;
    background: transparent;
    color: var(--color-foreground);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .custom-name {
    font-size: 14px;
    font-weight: 500;
  }
  .custom-caption {
    font-size: 12px;
    color: var(--color-muted-foreground);
  }
  .more {
    flex-shrink: 0;
    width: 32px;
    height: 32px;
    border: 0;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-muted-foreground);
    font: inherit;
    font-size: 16px;
    cursor: pointer;

    &:hover {
      color: var(--color-foreground);
    }
  }
  .menu {
    position: absolute;
    right: 4px;
    top: calc(100% - 4px);
    z-index: 5;
    display: flex;
    flex-direction: column;
    min-width: 140px;
    padding: 4px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: var(--color-inset);
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
  }
  .action {
    padding: 8px 10px;
    border: 0;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-text-2);
    font: inherit;
    font-size: 13px;
    text-align: left;
    cursor: pointer;

    &:hover {
      background: var(--color-card);
      color: var(--color-foreground);
    }

    &.destructive:hover {
      color: var(--color-accent);
    }
  }
  .factory-list {
    gap: 2px;
    overflow-y: auto;
  }
  .model-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px 6px 12px;
    border-radius: var(--radius);

    &.selected {
      background: var(--color-inset);
    }
  }
  .model-name {
    flex-grow: 1;
    min-width: 0;
    font-size: 15px;
    font-weight: 500;
  }
  .chips {
    display: flex;
    gap: 6px;
  }
  .star {
    width: 32px;
    height: 32px;
    border: 0;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-muted-foreground);
    font-size: 18px;
    line-height: 1;
    cursor: pointer;

    &:hover {
      color: var(--color-accent);
    }

    &.starred {
      color: var(--color-accent);
    }
  }
  .chip {
    height: 36px;
    padding: 0 12px;
    border-radius: 9px;
    border: 1px solid var(--color-border);
    background: transparent;
    color: var(--color-muted-foreground);
    font: inherit;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;

    &:hover {
      border-color: var(--color-accent);
      color: var(--color-accent);
    }

    &.selected {
      background: var(--color-accent);
      border-color: var(--color-accent);
      color: var(--color-on-accent);
    }
  }

  @media (min-width: 1200px) {
    :host {
      gap: 24px;
    }
    .search {
      height: 40px;
      border-radius: var(--radius);
    }
    .group {
      gap: 4px;
    }
    .model-name {
      font-size: 14px;
    }
    .chip {
      height: 28px;
      padding: 0 9px;
      border-radius: 7px;
      font-size: 12px;
    }
  }
`;
