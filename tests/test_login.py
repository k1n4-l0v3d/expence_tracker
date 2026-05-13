import pytest
from app import app as flask_app, db, rate_limiter
from app import User


@pytest.fixture
def existing_user():
    """Create a test user in the database."""
    with flask_app.app_context():
        u = User(username='alice', email='alice@example.com', role='user')
        u.set_password('secret123')
        db.session.add(u)
        db.session.commit()


def test_get_login_returns_200(client):
    response = client.get('/login')
    assert response.status_code == 200


def test_honeypot_filled_silently_rejected(client):
    response = client.post('/login', data={
        'username': 'alice', 'password': 'secret123',
        'website': 'http://bot.com',
    })
    assert response.status_code == 200
    assert b'alert-success' not in response.data


def test_blocked_ip_rejected(client):
    for _ in range(10):
        rate_limiter.record_failure('127.0.0.1')
    response = client.post('/login', data={
        'username': 'alice', 'password': 'secret123',
        'website': '',
    })
    assert 'много попыток'.encode() in response.data


def test_wrong_password_records_failure(client, existing_user):
    client.post('/login', data={
        'username': 'alice', 'password': 'wrong',
        'website': '',
    })
    assert rate_limiter._data.get('127.0.0.1', {}).get('count', 0) == 1


def test_successful_login_resets_rate_limiter(client, existing_user):
    rate_limiter.record_failure('127.0.0.1')
    client.post('/login', data={
        'username': 'alice', 'password': 'secret123',
        'website': '',
    }, follow_redirects=True)
    assert '127.0.0.1' not in rate_limiter._data


def test_successful_login_redirects(client, existing_user):
    response = client.post('/login', data={
        'username': 'alice', 'password': 'secret123',
        'website': '',
    })
    assert response.status_code == 302
