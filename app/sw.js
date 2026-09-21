const CACHE = 'opening-trainer-v11';
const ASSETS = ["./", "index.html", "style.css?v=10", "app.js?v=11", "coach.js?v=9", "public-puzzles.js?v=9", "puzzles-ui.js?v=9", "books.js?v=1", "repertoire.js", "pwa.js?v=4", "manifest.webmanifest", "pieces/bB.svg?v=11", "pieces/bK.svg?v=11", "pieces/bN.svg?v=11", "pieces/bP.svg?v=11", "pieces/bQ.svg?v=11", "pieces/bR.svg?v=11", "pieces/wB.svg?v=11", "pieces/wK.svg?v=11", "pieces/wN.svg?v=11", "pieces/wP.svg?v=11", "pieces/wQ.svg?v=11", "pieces/wR.svg?v=11", "icons/apple-touch-icon.png", "icons/icon-192.png", "icons/icon-512.png"];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS.map(url => new Request(url, {cache: 'reload'})))));
});
// Activation keeps the current lesson running; new scripts load on the next navigation.
self.addEventListener('message', event => {
  if (event.data === 'ACTIVATE_UPDATE') self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(
    keys.filter(key => key.startsWith('opening-trainer-') && key !== CACHE)
      .map(key => caches.delete(key))
  )).then(() => self.clients.claim()));
});
// Network first keeps lessons fresh; the cached copy supports offline training.
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET' || new URL(event.request.url).origin !== self.location.origin) return;
  event.respondWith(fetch(event.request, {cache: 'no-cache'}).then(response => {
    if (response.ok) {
      const copy = response.clone();
      event.waitUntil(caches.open(CACHE).then(cache => cache.put(event.request, copy)));
    }
    return response;
  }).catch(async () => {
    const cached = await caches.match(event.request);
    if(cached) return cached;
    // Versioned entry links must reopen offline on the very first visit too.
    if(event.request.mode === 'navigate') {
      const shell = await caches.match(new URL('index.html', self.registration.scope).href);
      if(shell) return shell;
    }
    return Response.error();
  }));
});
