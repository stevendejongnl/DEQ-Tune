// The app was a PWA until 2026-10-24, with a Workbox service worker at this
// address. A browser that installed it still has it, and it would keep
// serving its cached copy. A browser checks this address for an update on
// each visit, so it finds this worker. This worker deletes every cache,
// unregisters itself, and reloads each open page from the Pi. Remove this
// file once no browser can still hold the old worker.
self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const cacheNames = await caches.keys();
      await Promise.all(cacheNames.map((cacheName) => caches.delete(cacheName)));
      await self.registration.unregister();
      const windows = await self.clients.matchAll({ type: "window" });
      for (const client of windows) {
        client.navigate(client.url);
      }
    })(),
  );
});
