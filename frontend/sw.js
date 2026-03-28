const CACHE_VERSION = 2;
const CACHE_NAME = 'klaus-v' + CACHE_VERSION;
const APP_SHELL = [
    '/',
    '/index.html',
    '/css/app.css',
    '/js/app.js',
    '/js/audio-player.js',
    '/manifest.json',
    '/assets/icon-192.png',
    '/assets/icon-512.png',
    '/assets/klaus-avatar.png'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(APP_SHELL);
        })
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
            );
        })
    );
    self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Never cache API or WebSocket routes
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws/')) {
        event.respondWith(fetch(event.request));
        return;
    }

    // Cache-first strategy for app shell
    event.respondWith(
        caches.match(event.request).then((cached) => {
            if (cached) {
                // Update cache in background
                fetch(event.request).then((response) => {
                    if (response && response.status === 200) {
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(event.request, response);
                        });
                    }
                }).catch(() => {});
                return cached;
            }
            return fetch(event.request).then((response) => {
                if (response && response.status === 200) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, clone);
                    });
                }
                return response;
            });
        })
    );
});
