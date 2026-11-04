const CACHE='fieldnote-v4';
const ASSETS=['./','index.html','browse.html','market.html','style.css','common.js?v=4','today.js?v=4','browse.js?v=4','market.js?v=4','manifest.webmanifest','icon.svg','icon-192.png','icon-512.png'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS)).then(()=>self.skipWaiting())));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{if(event.request.method!=='GET'||new URL(event.request.url).origin!==location.origin)return;event.respondWith(fetch(event.request).then(response=>{if(response.ok){let copy=response.clone();caches.open(CACHE).then(cache=>cache.put(event.request,copy))}return response}).catch(()=>caches.match(event.request).then(cached=>cached||Response.error())))})
