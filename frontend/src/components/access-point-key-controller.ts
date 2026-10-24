import type { ReactiveController, ReactiveControllerHost } from "lit";
import type { WifiApi } from "../api/client.ts";
import type { AccessPointDto } from "../dto/profile.dto.ts";
import type { LocaleStorage } from "../i18n/locale.ts";

/** Set once the person put the access point setup off with "Later". */
export const ACCESS_POINT_SETUP_SKIPPED_KEY = "deq-tune.access-point-setup-skipped";

/** What app-root gives the controller. */
export interface AccessPointKeyHooks {
  api(): Pick<WifiApi, "readAccessPoint">;
  storage(): LocaleStorage;
}

/**
 * Asks for an own access point key while the Pi still uses the public
 * default key.
 *
 * app-root creates it with hooks and calls `load` once. The first time, the
 * setup step opens (`setupOpen`). "Later" calls `skip`, and from then on the
 * notification dock shows a notice (`showsNotice`) until the key changes.
 * Every saved key comes in through `accept`. It depends on the Wi-Fi API
 * and on browser storage for the skipped setup.
 */
export class AccessPointKeyController implements ReactiveController {
  accessPoint: AccessPointDto | null = null;
  setupOpen = false;

  private readonly host: ReactiveControllerHost;
  private readonly hooks: AccessPointKeyHooks;

  constructor(host: ReactiveControllerHost, hooks: AccessPointKeyHooks) {
    this.host = host;
    this.hooks = hooks;
    host.addController(this);
  }

  hostConnected(): void {}

  /** True while the default key is in use and the setup step is closed. */
  get showsNotice(): boolean {
    return this.accessPoint?.uses_default_key === true && !this.setupOpen;
  }

  /** Reads the access point. A Pi without one, or one that does not
   * answer, asks for nothing. */
  async load(): Promise<void> {
    try {
      this.accessPoint = await this.hooks.api().readAccessPoint();
    } catch {
      this.accessPoint = null;
    }
    this.setupOpen = this.accessPoint?.uses_default_key === true && !this.wasSkipped();
    this.host.requestUpdate();
  }

  /** Closes the setup step for good. The dock notice takes its place. */
  skip(): void {
    this.hooks.storage().setItem(ACCESS_POINT_SETUP_SKIPPED_KEY, "true");
    this.setupOpen = false;
    this.host.requestUpdate();
  }

  /** Takes the access point state after a saved key. */
  accept(accessPoint: AccessPointDto): void {
    this.accessPoint = accessPoint;
    this.host.requestUpdate();
  }

  /** Closes the setup step after a saved key. */
  closeSetup(): void {
    this.setupOpen = false;
    this.host.requestUpdate();
  }

  private wasSkipped(): boolean {
    return this.hooks.storage().getItem(ACCESS_POINT_SETUP_SKIPPED_KEY) !== null;
  }
}
