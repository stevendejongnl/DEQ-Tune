import { css } from "lit";
import { wifiSettingsStyles } from "./wifi-settings.styles.ts";

export const accessPointSettingsStyles = [
  wifiSettingsStyles,
  css`
    .intro {
      margin-top: 8px;
    }
    .warning {
      margin: 8px 0 0;
      padding: 8px 10px;
      border: 1px solid var(--color-warn-border);
      border-radius: var(--radius);
      background: var(--color-warn-bg);
      font-size: 13px;
      color: var(--color-foreground);
    }
    access-point-key-form {
      margin-top: 12px;
    }
  `,
];
