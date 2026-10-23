import type { UpdatesApi } from "../../api/client.ts";
import type { UpdatesDto } from "../../dto/profile.dto.ts";

/** What a machine with no updater answers, such as a laptop. */
export const NO_UPDATER: UpdatesDto = {
  supported: false,
  installed: null,
  latest: null,
  automatic: true,
  update_available: false,
  gadget_pending: false,
  notes: "",
  release_url: "",
  checked_at: "",
  last_result: "",
  history: [],
  frontend_build: null,
};

/** A Pi that the updater just moved from 1.15.0 to 1.16.0. */
export function updatedPi(overrides: Partial<UpdatesDto> = {}): UpdatesDto {
  return {
    supported: true,
    installed: "1.16.0",
    latest: "1.16.0",
    automatic: true,
    update_available: false,
    gadget_pending: false,
    notes: "### Features\n\n* the Pi installs each new release by itself ([2b265ca](https://example/2b265ca))",
    release_url: "https://github.com/example/releases/tag/v1.16.0",
    checked_at: "2026-10-23T14:07:18+00:00",
    last_result: "updated from 1.15.0 to 1.16.0",
    history: [{ from_version: "1.15.0", to_version: "1.16.0", at: "2026-10-23T14:07:18+00:00" }],
    frontend_build: null,
    ...overrides,
  };
}

/** An UpdatesApi that holds the updater's state in memory.
 *
 * `failWith` makes every next call throw that error, the way the real client
 * throws an `ApiError` for a 503. */
export class FakeUpdatesApi implements UpdatesApi {
  updates: UpdatesDto;
  failWith: Error | null = null;
  requests = 0;
  reads = 0;

  constructor(updates: UpdatesDto = NO_UPDATER) {
    this.updates = updates;
  }

  async readUpdates(): Promise<UpdatesDto> {
    this.throwIfFailing();
    this.reads += 1;
    return this.updates;
  }

  async setAutomaticUpdates(automatic: boolean): Promise<UpdatesDto> {
    this.throwIfFailing();
    this.updates = { ...this.updates, automatic };
    return this.updates;
  }

  async requestUpdate(): Promise<void> {
    this.throwIfFailing();
    this.requests += 1;
  }

  private throwIfFailing(): void {
    if (this.failWith !== null) {
      throw this.failWith;
    }
  }
}
