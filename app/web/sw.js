/* MediaBoss Service Worker：静态资源 cache-first，API 永不缓存（B8 PWA）。 */
const CACHE = "mb-static-v5";
const PRECACHE = [
  "/manifest.json",
  "/ico/icon-192.png",
  "/ico/icon-512.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  // API 与视频流一律直连网络，绝不缓存
  if (url.pathname.startsWith("/api/")) return;
  // 静态资源：cache-first，后台刷新
  e.respondWith(
    caches.match(e.request).then((hit) => {
      const fetching = fetch(e.request).then((res) => {
        if (res.ok && res.type === "basic") {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
        }
        return res;
      }).catch(() => hit);
      return hit || fetching;
    })
  );
});
