/**
 * IMAGEKEY - Optical Vault Service Worker (v1.2.0-sync)
 * Enables PWA / Mobile offline caching, high performance,
 * and zero-stale-cache bypass for dynamic APIs and live vaults.
 */

const CACHE_NAME = 'imagekey-v1.2.0-sync';
const PRECACHE_RESOURCES = [
  '/',
  '/scan',
  '/static/css/theme.css',
  '/static/js/theme.js',
  '/static/manifest.json',
  '/static/img/logo.png',
  '/static/img/icon-192.png',
  '/static/img/icon-512.png',
  '/static/img/icon.svg'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_RESOURCES))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            console.log('[SW] Purging outdated cache:', key);
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Listen for client broadcast messages (force skipWaiting or purge)
self.addEventListener('message', (event) => {
  if (!event.data) return;
  if (event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  if (event.data.type === 'CLEAR_CACHE') {
    caches.keys().then((keys) => {
      return Promise.all(keys.map((k) => caches.delete(k)));
    });
  }
});

self.addEventListener('fetch', (event) => {
  // Only handle GET requests
  if (event.request.method !== 'GET') return;

  const url = new URL(event.request.url);

  // CRITICAL: Bypass Service Worker completely for all dynamic API endpoints,
  // sync status checks, health checks, and stateful endpoints so they never stale.
  if (
    url.pathname.startsWith('/api') ||
    url.pathname.startsWith('/health') ||
    url.pathname.startsWith('/demo/')
  ) {
    return; // Pass through to live network
  }

  // Network-First with fallback for UI assets
  event.respondWith(
    fetch(event.request, { cache: 'no-cache' })
      .then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          // Only cache static assets (CSS, JS, images, fonts)
          if (url.pathname.startsWith('/static/')) {
            const responseToCache = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(event.request, responseToCache);
            });
          }
        }
        return networkResponse;
      })
      .catch(() => {
        // Fallback to cache when fully offline
        return caches.match(event.request).then((cachedResponse) => {
          if (cachedResponse) return cachedResponse;
          if (event.request.mode === 'navigate') {
            return caches.match('/scan') || caches.match('/');
          }
        });
      })
  );
});
