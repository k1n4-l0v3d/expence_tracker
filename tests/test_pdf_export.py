import pytest
from app import app as flask_app, db, User


def _register_and_login(client, username='pdfuser', password='pass1234'):
    client.post('/register', data={
        'username': username, 'email': f'{username}@example.com',
        'password': password, 'confirm': password,
    }, follow_redirects=True)
    client.post('/login', data={'login': username, 'password': password},
                follow_redirects=True)


def test_svg_donut_two_segments():
    """_svg_donut with two segments returns valid SVG with path elements."""
    from app import _svg_donut
    result = _svg_donut([
        {'color': '#4361ee', 'value': 500.0, 'label': 'Еда'},
        {'color': '#e8115b', 'value': 300.0, 'label': 'Кафе'},
    ])
    assert '<svg' in result
    assert '<path' in result
    assert '#4361ee' in result
    assert '#e8115b' in result


def test_svg_donut_empty_returns_circle():
    """_svg_donut with no segments returns grey circle fallback."""
    from app import _svg_donut
    result = _svg_donut([])
    assert '<svg' in result
    assert '<circle' in result
    assert '<path' not in result


def test_pdf_route_requires_month(client):
    """GET /profile/export/pdf with month=0 redirects to profile."""
    _register_and_login(client)
    resp = client.get('/profile/export/pdf?year=2026&month=0',
                      follow_redirects=False)
    assert resp.status_code == 302
    assert '/profile' in resp.headers['Location']


def test_pdf_route_returns_pdf(client):
    """GET /profile/export/pdf with valid month returns PDF content-type."""
    from unittest.mock import patch
    _register_and_login(client)
    with patch('app._render_pdf', return_value=b'%PDF-1.4 fake'):
        resp = client.get('/profile/export/pdf?year=2026&month=5')
    assert resp.status_code == 200
    assert resp.content_type == 'application/pdf'
    assert resp.data == b'%PDF-1.4 fake'
