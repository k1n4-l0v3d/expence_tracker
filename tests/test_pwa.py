import pytest
from app import app as flask_app


def _register_and_login(client, username='pwauser', password='pass1234'):
    client.post('/register', data={
        'username': username, 'email': f'{username}@example.com',
        'password': password, 'confirm': password,
    }, follow_redirects=True)
    client.post('/login', data={'login': username, 'password': password},
                follow_redirects=True)


def test_offline_route_no_auth(client):
    """GET /offline returns 200 without authentication."""
    resp = client.get('/offline')
    assert resp.status_code == 200
    assert 'Нет подключения'.encode() in resp.data


def test_manifest_returns_json(client):
    """GET /static/manifest.json returns valid PWA manifest."""
    resp = client.get('/static/manifest.json')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['display'] == 'standalone'
    assert data['name'] == 'Подсчитай!'
    assert len(data['icons']) >= 2


def test_sw_returns_js(client):
    """GET /static/sw.js returns JavaScript."""
    resp = client.get('/static/sw.js')
    assert resp.status_code == 200
    assert b'CACHE' in resp.data


def test_base_html_has_manifest_link(client):
    """Dashboard HTML includes PWA manifest link."""
    _register_and_login(client)
    resp = client.get('/')
    assert resp.status_code == 200
    assert b'rel="manifest"' in resp.data
    assert b'theme-color' in resp.data
