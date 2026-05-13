# PWA Support — Design Spec

**Date:** 2026-05-10
**Status:** Approved

---

## Problem

The app works in mobile browsers but cannot be installed on the home screen as a native-like app. There is also no friendly offline experience — browser shows a generic error page when there is no network.

## Solution

Add PWA support: `manifest.json` (installability) + service worker with network-first strategy (offline fallback page). Icons generated once via `cairocffi` (already available as a WeasyPrint dependency). No new runtime dependencies.

---

## New Files

| File | Purpose |
|------|---------|
| `static/manifest.json` | PWA manifest: name, icons, theme color, display mode |
| `static/sw.js` | Service worker: network-first, offline fallback |
| `static/icons/icon-192.png` | App icon for Android / Chrome install prompt |
| `static/icons/icon-512.png` | App icon for splash screen |
| `templates/offline.html` | Standalone offline page (no base.html) |
| `scripts/gen_pwa_icons.py` | One-time icon generator using cairocffi |
| `tests/test_pwa.py` | 4 PWA-specific tests |

## Modified Files

| File | Change |
|------|--------|
| `templates/base.html` | manifest link, theme-color meta, apple-touch-icon, SW registration JS |
| `app.py` | Add `GET /offline` route (no `@login_required`) |

---

## `static/manifest.json`

```json
{
  "name": "Трекер расходов",
  "short_name": "Расходы",
  "description": "Личный трекер доходов и расходов",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#4361ee",
  "orientation": "portrait",
  "icons": [
    {
      "src": "/static/icons/icon-192.png",
      "sizes": "192x192",
      "type": "image/png"
    },
    {
      "src": "/static/icons/icon-512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "any maskable"
    }
  ]
}
```

---

## `static/sw.js`

```javascript
const CACHE = 'expense-tracker-v1';
const OFFLINE_URL = '/offline';
const PRECACHE = [
    OFFLINE_URL,
    '/static/css/style.css',
    '/static/css/animations.css',
    '/static/icons/icon-192.png',
];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE).then(cache => cache.addAll(PRECACHE))
    );
    self.skipWaiting();
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', event => {
    const { request } = event;

    // Skip non-GET and API requests
    if (request.method !== 'GET') return;
    if (request.url.includes('/api/')) return;

    // Navigation: network-first, fallback to offline page
    if (request.mode === 'navigate') {
        event.respondWith(
            fetch(request).catch(() => caches.match(OFFLINE_URL))
        );
        return;
    }

    // Static assets: network-first, fallback to cache
    event.respondWith(
        fetch(request)
            .then(response => {
                const clone = response.clone();
                caches.open(CACHE).then(cache => cache.put(request, clone));
                return response;
            })
            .catch(() => caches.match(request))
    );
});
```

---

## `templates/offline.html`

Standalone HTML — no `{% extends %}`. Matches app visual style.

```html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Нет подключения — Трекер расходов</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f8f9fa;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 2rem;
    }
    .header {
      background: linear-gradient(135deg, #4361ee, #e8115b);
      color: #fff;
      width: 100%;
      max-width: 480px;
      border-radius: 16px;
      padding: 24px;
      margin-bottom: 32px;
      font-size: 1.2rem;
      font-weight: 700;
      letter-spacing: 0.5px;
    }
    .icon { font-size: 4rem; margin-bottom: 16px; }
    h1 { font-size: 1.5rem; font-weight: 700; color: #1a1a2e; margin-bottom: 8px; }
    p  { color: #6c757d; margin-bottom: 24px; }
    button {
      background: linear-gradient(135deg, #4361ee, #e8115b);
      color: #fff;
      border: none;
      border-radius: 8px;
      padding: 12px 32px;
      font-size: 1rem;
      cursor: pointer;
    }
  </style>
</head>
<body>
  <div class="header">💸 Трекер расходов</div>
  <div class="icon">📡</div>
  <h1>Нет подключения</h1>
  <p>Проверьте интернет-соединение и попробуйте снова.</p>
  <button onclick="window.location.reload()">Повторить</button>
</body>
</html>
```

---

## `scripts/gen_pwa_icons.py`

Run once: `python scripts/gen_pwa_icons.py`

Uses `cairocffi` (installed as WeasyPrint dependency) to render an SVG to PNG.

```python
#!/usr/bin/env python3
"""Generate PWA icons: static/icons/icon-192.png and icon-512.png."""
import os
import sys

# Ensure DYLD_LIBRARY_PATH is set on macOS before importing cairocffi
if sys.platform == 'darwin' and os.path.isdir('/opt/homebrew/lib'):
    os.environ.setdefault('DYLD_LIBRARY_PATH', '/opt/homebrew/lib')

import cairocffi as cairo

ICONS_DIR = os.path.join(os.path.dirname(__file__), '..', 'static', 'icons')

SVG_TEMPLATE = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {s} {s}">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#4361ee"/>
      <stop offset="100%" stop-color="#e8115b"/>
    </linearGradient>
  </defs>
  <rect width="{s}" height="{s}" rx="{r}" fill="url(#g)"/>
  <text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle"
        font-size="{fs}" fill="white">💸</text>
</svg>
"""


def gen_png(size: int, path: str) -> None:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    ctx     = cairo.Context(surface)

    # Diagonal gradient background (#4361ee → #e8115b)
    pat = cairo.LinearGradient(0, 0, size, size)
    pat.add_color_stop_rgb(0, 0x43/255, 0x61/255, 0xee/255)
    pat.add_color_stop_rgb(1, 0xe8/255, 0x11/255, 0x5b/255)

    ctx.rectangle(0, 0, size, size)
    ctx.set_source(pat)
    ctx.fill()

    surface.write_to_png(path)
    print(f"  ✓ {path} ({size}x{size})")


def main():
    os.makedirs(ICONS_DIR, exist_ok=True)
    print("Generating PWA icons...")
    gen_png(192, os.path.join(ICONS_DIR, 'icon-192.png'))
    gen_png(512, os.path.join(ICONS_DIR, 'icon-512.png'))
    print("Done.")


if __name__ == '__main__':
    main()
```

---

## `templates/base.html` changes

Add to `<head>` (after existing `<link>` tags):

```html
<meta name="theme-color" content="#4361ee">
<link rel="manifest" href="/static/manifest.json">
<link rel="apple-touch-icon" href="/static/icons/icon-192.png">
```

Add before `</body>`:

```javascript
<script>
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
        navigator.serviceWorker.register('/static/sw.js');
    });
}
</script>
```

---

## `app.py` — offline route

Add after existing profile routes:

```python
@app.route('/offline')
def offline_page():
    return render_template('offline.html')
```

No `@login_required` — the offline page must be reachable without a session.

---

## Tests (`tests/test_pwa.py`)

```python
def test_manifest_returns_json(client):
    resp = client.get('/static/manifest.json')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['display'] == 'standalone'
    assert data['name'] == 'Трекер расходов'

def test_sw_returns_js(client):
    resp = client.get('/static/sw.js')
    assert resp.status_code == 200
    assert b'serviceWorker' in resp.data or b'CACHE' in resp.data

def test_offline_route_no_auth(client):
    resp = client.get('/offline')
    assert resp.status_code == 200
    assert 'Нет подключения'.encode() in resp.data

def test_base_html_has_manifest_link(client):
    _register_and_login(client)
    resp = client.get('/')
    assert resp.status_code == 200
    assert b'rel="manifest"' in resp.data
```

---

## Out of Scope

- Background sync (adding expenses while offline)
- Push notifications
- Full offline mode (browsing old data without network)
- App store submission (Google Play TWA, Apple App Store)
