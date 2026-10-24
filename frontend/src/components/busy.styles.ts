import { css } from "lit";

/**
 * The loader on a control whose action waits on the Pi. A component sets
 * `aria-busy="true"` on the control while its request runs. The label hides,
 * so the control keeps its size, and a spinner turns in its place. Every
 * component with such an action adds these styles.
 */
export const busyStyles = css`
  :is(button, label)[aria-busy="true"] {
    position: relative;
    color: transparent !important;
    pointer-events: none;

    & > * {
      visibility: hidden;
    }

    &::after {
      content: "";
      position: absolute;
      inset: 0;
      width: 16px;
      height: 16px;
      margin: auto;
      box-sizing: border-box;
      border: 2px solid var(--color-text-2);
      border-top-color: transparent;
      border-radius: 50%;
      animation: busy-spin 0.7s linear infinite;
    }
  }

  @keyframes busy-spin {
    to {
      transform: rotate(360deg);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    :is(button, label)[aria-busy="true"]::after {
      animation-duration: 2s;
    }
  }
`;
