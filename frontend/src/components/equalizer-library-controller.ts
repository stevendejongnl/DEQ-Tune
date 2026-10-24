import type { ReactiveController, ReactiveControllerHost } from "lit";
import type { DeviceApi, EqualizerApi } from "../api/client.ts";
import type { ActiveProfileDto, EqualizerDto } from "../dto/profile.dto.ts";

/** The first edit of a factory EQ, or of No EQ, before its copy exists. */
interface EqualizerDraft {
  name: string;
  gains: number[];
}

/** What app-root gives the controller: the API, and the active state that
 * app-root keeps for the profile and the EQ together. */
export interface EqualizerLibraryHooks {
  api(): EqualizerApi & Pick<DeviceApi, "activateEqualizer">;
  activeEqualizerId(): number | null | undefined;
  setActive(state: ActiveProfileDto): void;
  reloadActive(): Promise<void>;
  /** The name for a new EQ that starts from No EQ. */
  newEqualizerName(): string;
}

/**
 * Keeps the EQ library on screen, and turns edits into saves.
 *
 * app-root creates it with hooks, and calls `load`, `activate`,
 * `setFavorite`, `changeGains`, `rename` and `remove`. It depends on the EQ
 * API and on app-root's active state.
 *
 * A factory EQ stays read-only, and No EQ is no EQ at all. So the first edit
 * of either makes a copy of the person's own, which then plays. Until that
 * copy exists, the edit lives in a draft, so quick edits make one copy and
 * lose no band. An EQ of the person's own saves through one queue, as a
 * profile does: the screen shows each edit at once.
 */
export class EqualizerLibraryController implements ReactiveController {
  equalizers: EqualizerDto[] = [];
  /** The EQ whose activation waits on the Pi (`id` null for No EQ), or
   * null while none waits. Its tile shows the loader. */
  activating: { id: number | null } | null = null;
  private draft: EqualizerDraft | null = null;
  private creatingCopy = false;
  private unsavedEdit: { id: number; gains?: number[]; name?: string } | null = null;
  private savingEdits = false;

  private readonly host: ReactiveControllerHost;
  private readonly hooks: EqualizerLibraryHooks;

  constructor(host: ReactiveControllerHost, hooks: EqualizerLibraryHooks) {
    this.host = host;
    this.hooks = hooks;
    host.addController(this);
  }

  hostConnected(): void {}

  /** The EQ that plays, as it shows: the draft while a copy is on its way. */
  get shown(): EqualizerDto | null {
    if (this.draft !== null) {
      return { id: -1, name: this.draft.name, source: "custom", favorite: false, gains: this.draft.gains };
    }
    return this.active ?? null;
  }

  get active(): EqualizerDto | undefined {
    const id = this.hooks.activeEqualizerId();
    return this.equalizers.find((equalizer) => equalizer.id === id);
  }

  async load(): Promise<void> {
    try {
      this.equalizers = await this.hooks.api().listEqualizers();
      this.host.requestUpdate();
    } catch {
      // The backend is out of reach. The library stays empty until the
      // next page load, and the header says why.
    }
  }

  async activate(id: number | null): Promise<void> {
    this.activating = { id };
    this.host.requestUpdate();
    try {
      this.hooks.setActive(await this.hooks.api().activateEqualizer(id));
    } catch {
      // The backend is out of reach. The status stays as it was.
    } finally {
      this.activating = null;
      this.host.requestUpdate();
    }
  }

  async setFavorite(id: number, favorite: boolean): Promise<void> {
    const updated = await this.hooks.api().setEqualizerFavorite(id, favorite);
    this.replace(updated);
  }

  /** A whole new curve for the EQ that plays. */
  async changeGains(gains: number[]): Promise<void> {
    const active = this.active;
    if (this.draft === null && active?.source === "custom") {
      await this.edit({ id: active.id, gains });
      return;
    }
    const base = this.draft?.name ?? (active === undefined ? this.hooks.newEqualizerName() : `${active.name} (copy)`);
    this.draft = { name: base, gains };
    this.host.requestUpdate();
    await this.createCopyFromDraft();
  }

  async rename(name: string): Promise<void> {
    const active = this.active;
    if (active?.source === "custom") {
      await this.edit({ id: active.id, name });
    }
  }

  async remove(id: number): Promise<void> {
    if (this.unsavedEdit?.id === id) {
      this.unsavedEdit = null;
    }
    await this.hooks.api().deleteEqualizer(id);
    this.equalizers = this.equalizers.filter((equalizer) => equalizer.id !== id);
    this.host.requestUpdate();
    // The backend forgets a deleted EQ that was playing.
    await this.hooks.reloadActive();
  }

  /** Creates the copy once, plays it, then sends the edits that came while
   * it was on its way. */
  private async createCopyFromDraft(): Promise<void> {
    if (this.creatingCopy || this.draft === null) {
      return;
    }
    this.creatingCopy = true;
    const sent = this.draft;
    try {
      const api = this.hooks.api();
      const created = await api.createEqualizer({ name: sent.name, gains: sent.gains });
      this.equalizers = [...this.equalizers, created];
      this.hooks.setActive(await api.activateEqualizer(created.id));
      const latest = this.draft;
      this.draft = null;
      if (latest !== null && latest.gains !== sent.gains) {
        await this.edit({ id: created.id, gains: latest.gains });
      }
    } catch {
      // The backend did not take the copy. The draft stays on screen, and
      // the next edit tries again.
    } finally {
      this.creatingCopy = false;
      this.host.requestUpdate();
    }
  }

  private async edit(change: { id: number; gains?: number[]; name?: string }): Promise<void> {
    this.equalizers = this.equalizers.map((equalizer) =>
      equalizer.id === change.id ? { ...equalizer, ...change } : equalizer,
    );
    this.host.requestUpdate();
    const pending = this.unsavedEdit;
    this.unsavedEdit = pending !== null && pending.id === change.id ? { ...pending, ...change } : change;
    await this.saveEdits();
  }

  private async saveEdits(): Promise<void> {
    if (this.savingEdits) {
      return;
    }
    this.savingEdits = true;
    let edit: { id: number; gains?: number[]; name?: string } | null = null;
    try {
      while (this.unsavedEdit !== null) {
        edit = this.unsavedEdit;
        this.unsavedEdit = null;
        const { id, ...body } = edit;
        await this.hooks.api().updateEqualizer(id, body);
        edit = null;
        // An edit of the playing EQ leaves the unit on the older version.
        if (id === this.hooks.activeEqualizerId()) {
          await this.hooks.reloadActive();
        }
      }
    } catch {
      // The backend did not take the edit. The screen keeps it, and so does
      // the queue, under any newer edit. The next edit sends it again.
      if (edit !== null) {
        const newer = this.unsavedEdit;
        this.unsavedEdit = newer !== null && newer.id === edit.id ? { ...edit, ...newer } : edit;
      }
    } finally {
      this.savingEdits = false;
    }
  }

  private replace(updated: EqualizerDto): void {
    this.equalizers = this.equalizers.map((equalizer) => (equalizer.id === updated.id ? updated : equalizer));
    this.host.requestUpdate();
  }
}
