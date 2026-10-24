import type { CommunityEntry, CommunityIndex, CommunityLibraryApi } from "../../api/community-library.ts";

/** A CommunityLibraryApi with its entries in memory. It fails each read
 * while `failing` is true, as a phone without internet does. */
export class FakeCommunityLibrary implements CommunityLibraryApi {
  failing = false;
  reads = 0;

  private readonly entries: CommunityEntry[];

  constructor(entries: CommunityEntry[]) {
    this.entries = entries;
  }

  async readIndex(): Promise<CommunityIndex> {
    this.reads += 1;
    if (this.failing) {
      throw new TypeError("Failed to fetch");
    }
    return { format: "deq-tune-community", version: 1, entries: this.entries };
  }
}
