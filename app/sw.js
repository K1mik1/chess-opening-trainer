const CACHE = 'opening-trainer-v3';
const ASSETS = ["./", "index.html", "style.css?v=3", "app.js", "coach.js", "repertoire.js", "pwa.js?v=3", "manifest.webmanifest", "pieces/bB.svg", "pieces/bK.svg", "pieces/bN.svg", "pieces/bP.svg", "pieces/bQ.svg", "pieces/bR.svg", "pieces/wB.svg", "pieces/wK.svg", "pieces/wN.svg", "pieces/wP.svg", "pieces/wQ.svg", "pieces/wR.svg", "icons/apple-touch-icon.png", "icons/icon-192.png", "icons/icon-512.png"];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS.map(url => new Request(url, {cache: 'reload'})))));
});
// This release only refreshes presentation assets; it can take over open tabs.
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
  }).catch(async () => (await caches.match(event.request)) || Response.error()));
});
