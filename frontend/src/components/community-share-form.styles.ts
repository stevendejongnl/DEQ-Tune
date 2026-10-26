import { css } from "lit";
import { wifiSettingsStyles } from "./wifi-settings.styles.ts";

export const communityShareFormStyles = [
  wifiSettingsStyles,
  css`
    :host {
      display: block;
      margin-top: 16px;
    }
    a {
      color: var(--color-accent);
    }
    .share {
      display: flex;
      flex-direction: column;
      gap: 12px;
      padding: 12px;
      border: 1px solid var(--color-border);
      border-radius: var(--radius);
      background: var(--color-inset);

      h3 {
        margin: 0;
        font-size: 14px;
      }
    }
    form {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    label {
      display: flex;
      flex-direction: column;
      gap: 4px;
      font-size: 13px;
    }
    select,
    textarea {
      padding: 8px 10px;
      border: 1px solid var(--color-border);
      border-radius: var(--radius);
      background: var(--color-card);
      color: var(--color-foreground);
      font: inherit;
      font-size: 15px;
    }
    select {
      height: 40px;
      padding-block: 0;
    }
    textarea {
      resize: vertical;

      &.entry {
        font-family: var(--font-mono);
        font-size: 12px;
      }
    }
    .steps {
      margin: 0;
      font-size: 14px;
      line-height: 1.45;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 12px;
    }
    .github {
      font-weight: 600;
    }
    .make {
      align-self: flex-end;
      border-color: var(--color-accent);
      background: var(--color-accent);
      color: var(--color-on-accent);
    }
    .message {
      margin: 0;
    }
  `,
];
