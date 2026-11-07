const CACHE = 'fieldnote-v9';
const ASSETS = ['./', 'index.html', 'browse.html', 'market.html', 'style.css?v=9', 'common.js?v=9', 'today.js?v=9', 'browse.js?v=9', 'market.js?v=9', 'manifest.webmanifest', 'icon.svg', 'icon-192.png', 'icon-512.png', 'data/status.json', 'data/history.csv'];
self.addEventListener('install', event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting())));
self.addEventListener('activate', event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('fieldnote-v') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim())));
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== location.origin || /\/data\/(status\.json|history\.csv)$/.test(url.pathname)) return;
  event.respondWith(fetch(event.request).then(response => {
    if (response.ok) { const copy = response.clone(); caches.open(CACHE).then(cache => cache.put(event.request, copy)); }
    return response;
  }).catch(() => caches.match(event.request).then(cached => cached || Response.error())));
});
