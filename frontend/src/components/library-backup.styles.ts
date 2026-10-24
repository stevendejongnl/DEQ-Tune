import { css } from "lit";
import { wifiSettingsStyles } from "./wifi-settings.styles.ts";

export const libraryBackupStyles = [
  wifiSettingsStyles,
  css`
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 16px;
    }
    /* The shared label rule stacks a label over its field. This label is a
       button around a hidden file input, so it lays out as a button. */
    .import {
      position: relative;
      display: inline-flex;
      flex-direction: row;
      align-items: center;
      justify-content: center;
      box-sizing: border-box;
      height: 36px;
      padding: 0 14px;
      border: 1px solid var(--color-border);
      border-radius: var(--radius);
      background: var(--color-card);
      color: var(--color-foreground);
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;

      &:hover {
        border-color: var(--color-border-strong);
      }
      input {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        opacity: 0;
        cursor: pointer;
      }
    }
  `,
];
