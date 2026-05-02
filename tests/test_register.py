import pytest
from app import app as flask_app, rate_limiter


VALID_FORM = {
    'username': 'testuser',
    'email': 'test@example.com',
    'password': 'password123',
    'confirm': 'password123',
    'captcha': '5',
    'website': '',
}


@pytest.fixture
def client_with_captcha(client):
    """Client with captcha_answer=5 pre-set in session."""
    with client.session_transaction() as sess:
        sess['captcha_answer'] = 5
    return client


def test_get_register_returns_captcha_question(client):
    response = client.get('/register')
    assert response.status_code == 200
    # Page must show arithmetic operator
    data = response.data.decode()
    assert any(op in data for op in ['+', '−', '×', '-']), "No captcha question found"


def test_honeypot_filled_silently_rejected(client_with_captcha):
    data = {**VALID_FORM, 'website': 'http://spam.com'}
    response = client_with_captcha.post('/register', data=data)
    assert response.status_code == 200
    assert b'\xd0\xa3\xd1\x81\xd0\xbf\xd0\xb5\xd1\x88\xd0\xbd' not in response.data  # "Успешн" not in page


def test_blocked_ip_rejected(client_with_captcha):
    for _ in range(10):
        rate_limiter.record_failure('127.0.0.1')
    response = client_with_captcha.post('/register', data=VALID_FORM)
    assert response.status_code == 200
    assert 'много попыток'.encode() in response.data


def test_wrong_captcha_rejected(client):
    with client.session_transaction() as sess:
        sess['captcha_answer'] = 5
    data = {**VALID_FORM, 'captcha': '99'}
    response = client.post('/register', data=data)
    assert response.status_code == 200
    assert 'капч'.encode() in response.data


def test_password_mismatch_records_failure(client_with_captcha):
    data = {**VALID_FORM, 'confirm': 'different'}
    client_with_captcha.post('/register', data=data)
    assert rate_limiter._data.get('127.0.0.1', {}).get('count', 0) == 1


def test_successful_registration(client_with_captcha):
    response = client_with_captcha.post('/register', data=VALID_FORM, follow_redirects=True)
    assert response.status_code == 200
    assert 'testuser'.encode() in response.data


def test_successful_registration_resets_rate_limiter(client_with_captcha):
    rate_limiter.record_failure('127.0.0.1')
    client_with_captcha.post('/register', data=VALID_FORM, follow_redirects=True)
    assert '127.0.0.1' not in rate_limiter._data
