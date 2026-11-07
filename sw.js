const CACHE = "fieldnote-v18";
const ASSETS = [
  "./",
  "index.html",
  "browse.html",
  "market.html",
  "methods.html",
  "style.css?v=18",
  "common.js?v=18",
  "today.js?v=18",
  "browse.js?v=18",
  "market.js?v=18",
  "manifest.webmanifest",
  "fonts/fonts.css",
  "fonts/rP2Yp2ywxg089UriI5-g4vlH9VoD8Cmcqbu0-K4.woff2",
  "fonts/rP2Yp2ywxg089UriI5-g4vlH9VoD8Cmcqbu6-K6h9Q.woff2",
  "fonts/xn7gYHE41ni1AdIRggOxSuXd.woff2",
  "fonts/xn7gYHE41ni1AdIRggSxSuXd.woff2",
  "fonts/xn7gYHE41ni1AdIRggexSg.woff2",
  "fonts/xn7gYHE41ni1AdIRggixSuXd.woff2",
  "fonts/xn7gYHE41ni1AdIRggmxSuXd.woff2",
  "fonts/xn7gYHE41ni1AdIRggqxSuXd.woff2",

  "icon.svg",
  "icon-192.png",
  "icon-512.png",
  "data/status.json",
  "data/history.csv",
];
self.addEventListener("install", (event) =>
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(ASSETS))
      .then(() => self.skipWaiting()),
  ),
);
self.addEventListener("activate", (event) =>
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith("fieldnote-v") && key !== CACHE)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  ),
);
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (
    event.request.method !== "GET" ||
    url.origin !== location.origin ||
    /\/data\/(status\.json|history\.csv)$/.test(url.pathname)
  )
    return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(() =>
        caches
          .match(event.request)
          .then((cached) => cached || Response.error()),
      ),
  );
});
