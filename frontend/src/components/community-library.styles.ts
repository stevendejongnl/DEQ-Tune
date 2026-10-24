import { css } from "lit";
import { wifiSettingsStyles } from "./wifi-settings.styles.ts";

export const communityLibraryStyles = [
  wifiSettingsStyles,
  css`
    a {
      color: var(--color-accent);
    }
    .retry {
      margin-top: 12px;
    }
    .filters {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 16px;
    }
    .kinds {
      display: flex;
      gap: 4px;

      button[aria-pressed="true"] {
        border-color: var(--color-accent);
        color: var(--color-accent);
      }
    }
    .search {
      flex: 1;
      min-width: 160px;
      height: 36px;
      font-size: 14px;
    }
    .entries {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin: 16px 0 0;
      padding: 0;
      list-style: none;
    }
    .entry {
      display: flex;
      flex-direction: column;
      gap: 6px;
      padding: 12px;
      border: 1px solid var(--color-border);
      border-radius: var(--radius);
      background: var(--color-inset);
    }
    .entry-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }
    .name {
      min-width: 0;
      overflow: hidden;
      font-weight: 600;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .car,
    .author {
      font-size: 12px;
      color: var(--color-muted-foreground);
    }
    .curve {
      width: 100%;
      height: 40px;

      .zero {
        stroke: var(--color-zero);
        stroke-width: 1;
        vector-effect: non-scaling-stroke;
      }
      polyline {
        fill: none;
        stroke: var(--color-accent);
        stroke-width: 2;
        vector-effect: non-scaling-stroke;
      }
    }
    .description {
      margin: 0;
      font-size: 13px;
      color: var(--color-text-2);
    }
    .warning {
      margin: 0;
      padding: 8px;
      border: 1px solid var(--color-warn-border);
      border-radius: var(--radius);
      background: var(--color-warn-bg);
      font-size: 12px;
      color: var(--color-text-2);
    }
    .entry-actions {
      display: flex;
      align-items: center;
      gap: 8px;

      .message {
        margin: 0;
      }
    }
    .add {
      border-color: var(--color-accent);
      background: var(--color-accent);
      color: var(--color-on-accent);
    }
  `,
];
