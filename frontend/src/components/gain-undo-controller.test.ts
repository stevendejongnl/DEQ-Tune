import { describe, expect, it } from "vitest";
import type { ReactiveController, ReactiveControllerHost } from "lit";
import { GainUndoController } from "./gain-undo-controller.ts";

/** A host that counts the renders that the controller asks for. */
class CountingHost implements ReactiveControllerHost {
  readonly controllers: ReactiveController[] = [];
  updateRequests = 0;
  readonly updateComplete = Promise.resolve(true);

  addController(controller: ReactiveController): void {
    this.controllers.push(controller);
  }

  removeController(): void {}

  requestUpdate(): void {
    this.updateRequests += 1;
  }
}

describe("GainUndoController", () => {
  it("keeps only the curve before the first change of a step", () => {
    const undo = new GainUndoController(new CountingHost());

    undo.startStep();
    undo.recordBefore([0, 0]);
    undo.recordBefore([1, 0]);
    undo.recordBefore([2, 0]);

    expect(undo.takeBack()).toEqual([0, 0]);
    expect(undo.canUndo).toBe(false);
  });

  it("gives the steps back newest first", () => {
    const undo = new GainUndoController(new CountingHost());
    undo.startStep();
    undo.recordBefore([0, 0]);
    undo.startStep();
    undo.recordBefore([1, 0]);

    expect(undo.takeBack()).toEqual([1, 0]);
    expect(undo.takeBack()).toEqual([0, 0]);
    expect(undo.takeBack()).toBeUndefined();
  });

  it("starts a new step with the first change after an undo", () => {
    const undo = new GainUndoController(new CountingHost());
    undo.startStep();
    undo.recordBefore([0, 0]);
    undo.takeBack();

    undo.recordBefore([5, 5]);

    expect(undo.takeBack()).toEqual([5, 5]);
  });

  it("drops every step on clear", () => {
    const undo = new GainUndoController(new CountingHost());
    undo.startStep();
    undo.recordBefore([0, 0]);

    undo.clear();

    expect(undo.canUndo).toBe(false);
  });

  it("asks its host to render when Undo becomes possible", () => {
    const host = new CountingHost();
    const undo = new GainUndoController(host);

    undo.startStep();
    undo.recordBefore([0, 0]);

    expect(host.controllers).toEqual([undo]);
    expect(host.updateRequests).toBe(1);
  });
});
