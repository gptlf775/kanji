// 누구나 오픽 — 오프라인 동작 (인터넷 우선 → 실패하면 저장본)
const CACHE = 'opic-v1';
const CORE = ['./', './index.html', './manifest.webmanifest', './icons/icon-180.png', './icons/icon-192.png', './icons/icon-512.png', './data/opic.js', './data/ver.js'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => Promise.all(CORE.map(u => c.add(u).catch(() => {})))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith('opic-') && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== location.origin) return;
  e.respondWith(caches.open(CACHE).then(async c => {
    try { const res = await fetch(req, { cache: 'no-cache' }); if (res.ok) c.put(req, res.clone()); return res; }
    catch (err) { const hit = await c.match(req, { ignoreSearch: true }); return hit || new Response('오프라인 상태예요', { status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' } }); }
  }));
});
