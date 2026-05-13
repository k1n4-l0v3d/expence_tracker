var CACHE = 'expense-tracker-v1';
var OFFLINE_URL = '/offline';
var PRECACHE = [
    OFFLINE_URL,
    '/static/css/style.css',
    '/static/css/animations.css',
    '/static/icons/icon-192.png',
];

self.addEventListener('install', function(event) {
    event.waitUntil(
        caches.open(CACHE).then(function(cache) {
            return cache.addAll(PRECACHE);
        })
    );
    self.skipWaiting();
});

self.addEventListener('activate', function(event) {
    event.waitUntil(
        caches.keys().then(function(keys) {
            return Promise.all(
                keys.filter(function(k) { return k !== CACHE; })
                    .map(function(k) { return caches.delete(k); })
            );
        })
    );
    self.clients.claim();
});

self.addEventListener('fetch', function(event) {
    var request = event.request;

    // Skip non-GET and API requests
    if (request.method !== 'GET') return;
    if (request.url.indexOf('/api/') !== -1) return;

    // Navigation: network-first, fallback to offline page
    if (request.mode === 'navigate') {
        event.respondWith(
            fetch(request).catch(function() {
                return caches.match(OFFLINE_URL);
            })
        );
        return;
    }

    // Static assets: network-first, update cache, fallback to cache
    event.respondWith(
        fetch(request).then(function(response) {
            var clone = response.clone();
            caches.open(CACHE).then(function(cache) {
                cache.put(request, clone);
            });
            return response;
        }).catch(function() {
            return caches.match(request);
        })
    );
});
