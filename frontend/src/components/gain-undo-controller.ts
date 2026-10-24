import type { ReactiveController, ReactiveControllerHost } from "lit";

/**
 * Keeps the curves before each edit step of one EQ curve, so Undo can go
 * back one step at a time.
 *
 * A host creates it and calls `startStep` on each `gain-edit-start` of its
 * `eq-editor`, `recordBefore` with the curve before each `gain-change`, and
 * `takeBack` for Undo. One step is one drag, one tap on − or +, or one key.
 * It depends only on the host, which it asks to render when Undo becomes
 * possible or impossible.
 */
export class GainUndoController implements ReactiveController {
  private readonly host: ReactiveControllerHost;
  /** The curve before each edit step, the newest last. */
  private steps: number[][] = [];
  /** True once the current edit step saved its curve to `steps`. */
  private stepSaved = false;

  constructor(host: ReactiveControllerHost) {
    this.host = host;
    host.addController(this);
  }

  hostConnected(): void {}

  get canUndo(): boolean {
    return this.steps.length > 0;
  }

  /** Starts a new edit step. The next `recordBefore` saves its curve. */
  startStep(): void {
    this.stepSaved = false;
  }

  /** Saves `gains` as the curve before the current step, once per step. A
   * drag sends many changes, and only the curve before the first counts. */
  recordBefore(gains: readonly number[]): void {
    if (this.stepSaved) {
      return;
    }
    this.steps = [...this.steps, [...gains]];
    this.stepSaved = true;
    this.host.requestUpdate();
  }

  /** Removes the newest step and returns its curve, or `undefined` when no
   * step is left. */
  takeBack(): number[] | undefined {
    const previous = this.steps.at(-1);
    if (previous === undefined) {
      return undefined;
    }
    this.steps = this.steps.slice(0, -1);
    this.stepSaved = false;
    this.host.requestUpdate();
    return previous;
  }

  /** Drops every step, for example when another curve comes in. */
  clear(): void {
    this.steps = [];
    this.stepSaved = false;
    this.host.requestUpdate();
  }
}
