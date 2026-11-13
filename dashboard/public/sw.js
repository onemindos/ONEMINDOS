// SPDX-License-Identifier: Apache-2.0
// OneMind dashboard service worker. Its only job is to let the installed app open its own screens
// quickly and show the shell when the box is unreachable. It caches STATIC files only.
//
// Hard rules (tested in src/pwa.test.ts):
//  - Never cache or even touch anything under /v1/, /healthz, /mcp or /openapi.json: API answers
//    are private to the signed-in person and must always come live from the hub.
//  - Never handle a request that carries an Authorization header, any non-GET request, or any
//    other origin.
//  - A navigation is network-first; the cached page (the app shell, no data, no tokens) is only
//    used when the network fails, so a stale shell never hides a new release.
const CACHE = 'onemind-shell-v1';
const API = /^\/(v1\/|healthz$|mcp$|openapi\.json$)/;
const STATIC = /^\/(assets\/|brand\/|manifest\.webmanifest$)/;

function handles(request, url, origin) {
  if (request.method !== 'GET') return false;
  if (url.origin !== origin) return false;
  if (API.test(url.pathname)) return false;
  if (request.headers.has('authorization')) return false;
  return request.mode === 'navigate' || STATIC.test(url.pathname);
}

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (!handles(request, url, self.location.origin)) return;
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((res) => {
          if (res.ok && res.type === 'basic') {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put('/', copy));
          }
          return res;
        })
        .catch(() => caches.match('/').then((r) => r || Response.error())),
    );
    return;
  }
  // Hashed build files and brand images never change under the same name: cache first.
  event.respondWith(
    caches.match(request).then(
      (hit) =>
        hit ||
        fetch(request).then((res) => {
          if (res.ok && res.type === 'basic') {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(request, copy));
          }
          return res;
        }),
    ),
  );
});
