import { css } from "lit";
import { updateSettingsStyles } from "./update-settings.styles.ts";

export const bluetoothSettingsStyles = [
  updateSettingsStyles,
  css`
    .window {
      margin: 16px 0 0;
      font-size: 14px;

      &.open {
        color: var(--color-accent);
        font-weight: 600;
      }
    }
    .row {
      margin-top: 16px;
    }
    .phones {
      margin-top: 12px;
      padding-left: 20px;
      font-size: 14px;
    }
  `,
];
