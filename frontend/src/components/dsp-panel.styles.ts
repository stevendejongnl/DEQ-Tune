import { css } from "lit";

export const dspPanelStyles = css`
  :host {
    display: block;
  }
  .panel {
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    gap: 20px;
    padding: 16px;
    border: 1px solid var(--color-divider);
    border-radius: var(--radius-lg);
    background: var(--color-card);
  }
  .styles-column,
  .simulation-column {
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-width: 0;
  }
  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }
  h2 {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
  }
  .suffix {
    font-weight: 400;
    color: var(--color-muted-foreground);
  }
  .lock-note {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--color-muted-foreground);
  }
  .tiles {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }
  .tile {
    height: 48px;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 12px;
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border);
    background: var(--color-inset);
    color: var(--color-text-2);
    font: inherit;
    font-size: 13px;
    font-weight: 500;
    text-align: left;
    cursor: pointer;

    .radio {
      flex-shrink: 0;
      width: 14px;
      height: 14px;
      box-sizing: border-box;
      border-radius: 50%;
      border: 1.5px solid var(--color-outline);
    }

    &.selected {
      background: color-mix(in srgb, var(--color-accent) 10%, transparent);
      border-color: var(--color-accent);
      color: var(--color-foreground);

      .radio {
        border: 4px solid var(--color-accent);
      }
    }
  }
  .options {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .option {
    height: 44px;
    padding: 0 16px;
    border-radius: var(--radius-pill);
    border: 1px solid var(--color-border);
    background: transparent;
    color: var(--color-text-2);
    font: inherit;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;

    &.selected {
      background: var(--color-border-strong);
      border-color: var(--color-idle);
      color: var(--color-foreground);
    }
  }

  @media (min-width: 700px) {
    .panel {
      padding: 20px 24px;
    }
  }

  @media (min-width: 1200px) {
    .panel {
      display: grid;
      grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
      gap: 32px;
    }
    .tiles {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
    .tile {
      height: 44px;
      border-radius: var(--radius);

      .radio {
        width: 12px;
        height: 12px;
      }
    }
    .options {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 4px;
      padding: 4px;
      border-radius: var(--radius-md);
      background: var(--color-inset);
      border: 1px solid var(--color-border);
    }
    .option {
      height: 40px;
      padding: 0;
      border: 0;
      border-radius: 8px;
      font-size: 13px;
      color: var(--color-muted-foreground);

      &.selected {
        background: var(--color-border-strong);
        color: var(--color-foreground);
      }
    }
  }
  .library-toggle {
    margin-top: 12px;
    height: 34px;
    padding: 0 14px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius);
    background: transparent;
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
  .library {
    display: flex;
    flex-direction: column;
    gap: 2px;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .library-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 2px 4px 2px 0;
    border-radius: var(--radius);

    &.selected {
      background: var(--color-inset);
    }
  }
  .library-name {
    flex-grow: 1;
    min-height: 40px;
    padding: 0 12px;
    border: 0;
    background: transparent;
    color: var(--color-foreground);
    font: inherit;
    font-size: 14px;
    text-align: left;
    cursor: pointer;
  }
  .star {
    width: 36px;
    height: 36px;
    border: 0;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-muted-foreground);
    font-size: 18px;
    cursor: pointer;

    &.starred,
    &:hover {
      color: var(--color-accent);
    }
  }
`;
