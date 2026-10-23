import type { ReactiveController, ReactiveControllerHost } from "lit";
import { ApiError, type UpdatesApi } from "../api/client.ts";
import type { UpdatesDto } from "../dto/profile.dto.ts";
import type { LocaleStorage } from "../i18n/locale.ts";
import type { CancelFunction, ScheduleFunction } from "./device-status.ts";

/** How often the app reads the updater's state again. The updater itself
 * runs every 30 minutes, so a shorter gap only finds the same answer. */
export const UPDATES_REFRESH_MS = 10 * 60 * 1000;

/** The release that this browser already showed the "what's new" note for. */
export const SEEN_VERSION_KEY = "deq-tune.seen-version";
/** The release whose "update available" note the person put off. */
export const POSTPONED_VERSION_KEY = "deq-tune.postponed-version";
/** The bridge build that this browser last reloaded for. A second reload
 * for the same build would loop, for example in a car app whose own copy
 * is still older. */
export const RELOADED_FOR_KEY = "deq-tune.reloaded-for-build";

export type UpdateRequestState = "idle" | "busy" | "requested" | "failed" | "unsupported";

/** What app-root gives the controller. */
export interface UpdatesHooks {
  api(): UpdatesApi;
  storage(): LocaleStorage;
  scheduleFunction(): ScheduleFunction;
  cancelFunction(): CancelFunction;
  /** The build id of the page on screen. */
  pageBuild(): string;
  /** True while the person has edits that a reload would lose. */
  hasUnsavedEdits(): boolean;
  reload(): void;
}

/**
 * Keeps the Pi updater's state on screen, and turns the person's choices
 * into requests.
 *
 * app-root creates it with hooks. The settings page and the notification
 * dock read `updates`, `whatsNewVersion` and `availableVersion`, and their
 * events end in `setAutomatic`, `requestUpdate`, `dismissWhatsNew` and
 * `postpone`. It depends on the updates API, on browser storage for the
 * remembered versions, and on a scheduler that a test replaces.
 *
 * It also keeps the page current. When the bridge serves another build than
 * the one on screen, the page reloads, so a person never works in an old
 * copy while the bridge answers. It waits while there are unsaved edits,
 * and reloads once per build at most.
 */
export class UpdatesController implements ReactiveController {
  updates: UpdatesDto | null = null;
  requestState: UpdateRequestState = "idle";

  private readonly host: ReactiveControllerHost;
  private readonly hooks: UpdatesHooks;
  private refreshHandle: unknown;

  constructor(host: ReactiveControllerHost, hooks: UpdatesHooks) {
    this.host = host;
    this.hooks = hooks;
    host.addController(this);
  }

  hostConnected(): void {
    void this.loadAndScheduleNext();
    globalThis.document?.addEventListener("visibilitychange", this.onVisibilityChange);
  }

  hostDisconnected(): void {
    globalThis.document?.removeEventListener("visibilitychange", this.onVisibilityChange);
    if (this.refreshHandle !== undefined) {
      this.hooks.cancelFunction()(this.refreshHandle);
      this.refreshHandle = undefined;
    }
  }

  /** The release to announce, once: the one the Pi just installed. */
  get whatsNewVersion(): string | null {
    const installed = this.updates?.installed ?? null;
    const lastUpdate = this.updates?.history[0];
    if (installed === null || lastUpdate === undefined || lastUpdate.to_version !== installed) {
      return null;
    }
    return this.hooks.storage().getItem(SEEN_VERSION_KEY) === installed ? null : installed;
  }

  /** A newer release that waits for the Update button, unless put off. */
  get availableVersion(): string | null {
    const updates = this.updates;
    if (updates === null || updates.automatic || !updates.update_available || updates.latest === null) {
      return null;
    }
    return this.hooks.storage().getItem(POSTPONED_VERSION_KEY) === updates.latest ? null : updates.latest;
  }

  async load(): Promise<void> {
    try {
      this.updates = await this.hooks.api().readUpdates();
    } catch {
      // The Pi is out of reach. The last answer stays on screen.
    }
    this.host.requestUpdate();
    this.reloadWhenOutdated();
  }

  /** Reloads into the build that the bridge serves, when it differs. */
  reloadWhenOutdated(): void {
    const served = this.updates?.frontend_build ?? null;
    if (served === null || served === this.hooks.pageBuild() || this.hooks.hasUnsavedEdits()) {
      return;
    }
    const storage = this.hooks.storage();
    if (storage.getItem(RELOADED_FOR_KEY) === served) {
      return;
    }
    storage.setItem(RELOADED_FOR_KEY, served);
    this.hooks.reload();
  }

  /** A phone that comes back to the app may have missed a release. */
  private onVisibilityChange = (): void => {
    if (globalThis.document?.visibilityState === "visible") {
      void this.load();
    }
  };

  async setAutomatic(automatic: boolean): Promise<void> {
    try {
      this.updates = await this.hooks.api().setAutomaticUpdates(automatic);
    } catch {
      this.requestState = "failed";
    }
    this.host.requestUpdate();
  }

  async requestUpdate(): Promise<void> {
    this.requestState = "busy";
    this.host.requestUpdate();
    try {
      await this.hooks.api().requestUpdate();
      this.requestState = "requested";
    } catch (caughtError) {
      this.requestState = caughtError instanceof ApiError && caughtError.status === 503 ? "unsupported" : "failed";
    }
    this.host.requestUpdate();
  }

  dismissWhatsNew(version: string): void {
    this.hooks.storage().setItem(SEEN_VERSION_KEY, version);
    this.host.requestUpdate();
  }

  postpone(version: string): void {
    this.hooks.storage().setItem(POSTPONED_VERSION_KEY, version);
    this.host.requestUpdate();
  }

  private async loadAndScheduleNext(): Promise<void> {
    await this.load();
    this.refreshHandle = this.hooks.scheduleFunction()(() => {
      void this.loadAndScheduleNext();
    }, UPDATES_REFRESH_MS);
  }
}
