import { css } from "lit";
import { wifiSettingsStyles } from "./wifi-settings.styles.ts";

export const accessPointKeyFormStyles = [
  wifiSettingsStyles,
  css`
    :host {
      display: block;
    }
  `,
];
