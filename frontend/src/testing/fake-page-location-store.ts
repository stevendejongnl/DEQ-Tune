import type { PageLocationStore } from "../page-location.ts";

/** An in-memory PageLocationStore. `hash` holds what the page wrote last. */
export interface FakePageLocationStore extends PageLocationStore {
  hash: string;
}

export function createFakePageLocationStore(initialHash = ""): FakePageLocationStore {
  const store: FakePageLocationStore = {
    hash: initialHash,
    read: () => store.hash,
    write(hash) {
      store.hash = hash;
    },
  };
  return store;
}
