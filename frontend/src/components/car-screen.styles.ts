import { css } from "lit";

/**
 * The car screen fills Android Auto's display of about 650 × 370 CSS
 * pixels, in landscape: a bar on top, the tabs down the left side (the
 * driver's side of a left-hand-drive car), and the tiles beside them. Each
 * target is at least 56 pixels high, for a finger on a car screen.
 */
export const carScreenStyles = css`
  :host {
    display: flex;
    flex-direction: column;
    flex-grow: 1;
    height: 100vh;
    height: 100dvh;
    min-width: 0;
    background: var(--color-background);
    color: var(--color-foreground);
  }
  .bar {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 6px 12px;
    border-bottom: 1px solid var(--color-divider);
  }
  .now-playing {
    flex-grow: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;

    span {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }
  .now-profile {
    font-size: 16px;
    font-weight: 600;
  }
  .now-equalizer {
    font-size: 13px;
    color: var(--color-muted-foreground);
  }
  .body {
    flex-grow: 1;
    min-height: 0;
    display: flex;
  }
  .tabs {
    flex-shrink: 0;
    width: 112px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 8px;
    border-right: 1px solid var(--color-divider);
    background: var(--color-sidebar);
  }
  .tab {
    flex: 1 1 0;
    min-height: 56px;
    border-radius: var(--radius-md);
    border: 1px solid transparent;
    background: transparent;
    color: var(--color-text-2);
    font: inherit;
    font-size: 16px;
    font-weight: 500;
    cursor: pointer;

    &[aria-pressed="true"] {
      background: var(--color-inset);
      border-color: var(--color-accent);
      color: var(--color-foreground);
    }
  }
  .content {
    flex-grow: 1;
    min-width: 0;
    overflow-y: auto;
    padding: 10px;
  }
  .tiles {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 8px;
  }
  .tile {
    min-height: 64px;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    justify-content: center;
    gap: 6px;
    padding: 8px 14px;
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border);
    background: var(--color-inset);
    color: var(--color-text-2);
    font: inherit;
    font-size: 16px;
    font-weight: 500;
    text-align: left;
    cursor: pointer;

    &.selected {
      background: color-mix(in srgb, var(--color-accent) 12%, transparent);
      border-color: var(--color-accent);
      color: var(--color-foreground);
    }
  }
  .tile-name {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .curve {
    width: 60px;
    height: 20px;

    polyline {
      fill: none;
      stroke: var(--color-accent);
      stroke-width: 1.6;
      stroke-linejoin: round;
    }
    .zero {
      stroke: var(--color-zero);
      stroke-width: 1;
    }
  }
  .audio {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 24px;
    height: 100%;
    flex-wrap: wrap;
  }
  .volume {
    display: flex;
    align-items: center;
    gap: 16px;
  }
  .step,
  .mute {
    min-width: 72px;
    height: 72px;
    border-radius: var(--radius-lg);
    border: 1px solid var(--color-border-strong);
    background: var(--color-card);
    color: var(--color-foreground);
    font: inherit;
    font-size: 28px;
    cursor: pointer;

    &:disabled {
      color: var(--color-muted-foreground);
      cursor: not-allowed;
    }
  }
  .mute {
    padding: 0 20px;
    font-size: 18px;

    &.selected {
      border-color: var(--color-accent);
      color: var(--color-accent);
    }
  }
  .volume-value {
    min-width: 96px;
    text-align: center;
    font-family: var(--font-mono);
    font-size: 24px;
  }
  .empty {
    margin: 0;
    padding: 16px;
    font-size: 15px;
    color: var(--color-muted-foreground);
  }
`;
