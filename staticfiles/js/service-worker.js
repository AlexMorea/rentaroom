// Rooms4You service worker.
//
// Deliberately simple, matching the "don't over-engineer" brief:
// - Static assets (CSS/JS/images) -> cache-first (they're already
//   cache-busted with ?v= query strings, so stale content isn't a risk).
// - Page navigations -> network-first, falling back to a cached copy
//   or the offline page if the network is unavailable. Room listings,
//   prices, and availability change constantly - showing a stale cached
//   page as the DEFAULT behavior would actively mislead users about
//   what rooms are actually still available.
//
// Bump CACHE_NAME whenever this file changes, so old caches get cleared.
const CACHE_NAME = "rooms4you-v4";
const OFFLINE_URL = "/offline/";

const PRECACHE_URLS = [
  OFFLINE_URL,
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

function isStaticAsset(request) {
  return (
    request.destination === "style" ||
    request.destination === "script" ||
    request.destination === "image" ||
    request.destination === "font"
  );
}

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Only handle GET requests - never intercept form POSTs (placement
  // updates, room creation, contact forms, etc.) so they always hit
  // the network directly.
  if (request.method !== "GET") return;

  if (request.mode === "navigate") {
    // Page navigation: network-first, offline page as last resort.
    event.respondWith(
      fetch(request).catch(() =>
        caches.match(OFFLINE_URL)
      )
    );
    return;
  }

  if (isStaticAsset(request)) {
    // Static asset: cache-first, since these are already versioned
    // with ?v= query strings - a cached hit is always the right file.
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        });
      })
    );
  }
  // Everything else (API-like fetches, etc.) - let it pass through
  // untouched, no caching behavior applied.
});

// ---------------------------------------------------------------------
// Web Push - shows a notification for whatever the server sent
// (accounts.push.send_web_push always sends {title, body, url} JSON).
// Falls back to generic text if the payload is missing/malformed so a
// push never silently does nothing.
// ---------------------------------------------------------------------
self.addEventListener("push", (event) => {
  let data = { title: "Rooms4You", body: "You have a new notification.", url: "/" };

  if (event.data) {
    try {
      data = { ...data, ...event.data.json() };
    } catch (e) {
      data.body = event.data.text();
    }
  }

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "/static/images/icon-192.png",
      badge: "/static/images/icon-192.png",
      data: { url: data.url },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/";

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if (client.url === url && "focus" in client) return client.focus();
      }
      return self.clients.openWindow(url);
    })
  );
});
