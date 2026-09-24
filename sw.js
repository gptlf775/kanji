// 오프라인 동작용 서비스 워커
// 전략: 캐시에서 즉시 보여주고(오프라인 OK), 인터넷이 되면 뒤에서 새 버전으로 갱신
const CACHE = 'kanji1026-v1';
const CORE = ['./', './index.html', './manifest.webmanifest',
  './icons/icon-180.png', './icons/icon-192.png', './icons/icon-512.png'];
const DATA = ['./data/index.js', ...[1, 2, 3, 4, 5, 6].map(g => `./data/g${g}.js`)];  // 없는 학년은 건너뜀

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(async c => {
    await c.addAll(CORE);
    await Promise.all(DATA.map(u => c.add(u).catch(() => {})));
  }).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// 인터넷 우선(최신 버전 즉시 반영) → 실패하면 저장본(오프라인)
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== location.origin) return;
  e.respondWith(caches.open(CACHE).then(async c => {
    try {
      const res = await fetch(req, { cache: 'no-cache' });
      if (res.ok) c.put(req, res.clone());
      return res;
    } catch (err) {
      const hit = await c.match(req, { ignoreSearch: true });
      return hit || new Response('오프라인 상태예요', { status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
    }
  }));
});
