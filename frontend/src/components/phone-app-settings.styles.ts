import { css } from "lit";
import { wifiSettingsStyles } from "./wifi-settings.styles.ts";

export const phoneAppSettingsStyles = [
  wifiSettingsStyles,
  css`
    .status,
    .footer,
    .warning {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      font-size: 14px;
    }
    .warning {
      margin-top: 12px;
      padding: 8px 10px;
      border: 1px solid var(--color-warn-border);
      border-radius: var(--radius);
      background: var(--color-warn-bg);
      font-size: 13px;
    }
    .modes {
      margin: 20px 0 0;
      padding: 0;
      border: 0;

      legend {
        padding: 0;
        font-size: 14px;
        font-weight: 600;
        color: var(--color-text-2);
      }
    }
    .mode {
      flex-direction: row;
      align-items: flex-start;
      gap: 10px;
      padding: 10px 0;
      border-bottom: 1px solid var(--color-divider);
      cursor: pointer;

      input {
        height: auto;
        margin-top: 3px;
        accent-color: var(--color-accent);
      }
      > span {
        display: flex;
        flex-direction: column;
        gap: 2px;
      }
    }
    .mode-label {
      font-size: 15px;
      color: var(--color-foreground);
    }
    .hint {
      margin: 0;
    }
    .footer {
      margin-top: 24px;
    }
  `,
];
