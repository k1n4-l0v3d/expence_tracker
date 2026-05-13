import pytest
from datetime import date
from unittest.mock import patch


def test_next_payment_date_future():
    """Если день выплаты ещё не наступил — возвращает дату в этом месяце."""
    from app import next_payment_date
    today = date(2026, 4, 18)
    with patch('app.date') as mock_date:
        mock_date.today.return_value = today
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        result = next_payment_date(25)
    assert result == date(2026, 4, 25)


def test_next_payment_date_past():
    """Если день выплаты уже прошёл — возвращает дату в следующем месяце."""
    from app import next_payment_date
    today = date(2026, 4, 18)
    with patch('app.date') as mock_date:
        mock_date.today.return_value = today
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        result = next_payment_date(10)
    assert result == date(2026, 5, 10)


def test_next_payment_date_today():
    """Если день выплаты сегодня — возвращает следующий месяц."""
    from app import next_payment_date
    today = date(2026, 4, 18)
    with patch('app.date') as mock_date:
        mock_date.today.return_value = today
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        result = next_payment_date(18)
    assert result == date(2026, 5, 18)


def test_next_payment_date_overflow():
    """День 31 в феврале → последний день февраля."""
    from app import next_payment_date
    today = date(2026, 2, 5)
    with patch('app.date') as mock_date:
        mock_date.today.return_value = today
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        result = next_payment_date(31)
    assert result == date(2026, 2, 28)


def test_get_daily_budget_no_days():
    """Если обе даты не заданы — возвращает None."""
    from app import get_daily_budget_info
    result = get_daily_budget_info(balance=5000.0, salary_day=None, advance_day=None)
    assert result is None


def test_get_daily_budget_positive():
    """Положительный баланс делится на дни до ближайшей выплаты."""
    from app import get_daily_budget_info
    today = date(2026, 4, 18)
    with patch('app.date') as mock_date:
        mock_date.today.return_value = today
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        result = get_daily_budget_info(balance=700.0, salary_day=None, advance_day=25)
    assert result['daily'] == pytest.approx(100.0)
    assert result['days_left'] == 7
    assert result['payment_type'] == 'аванса'


def test_get_daily_budget_negative():
    """Отрицательный баланс → отрицательная дневная сумма."""
    from app import get_daily_budget_info
    today = date(2026, 4, 18)
    with patch('app.date') as mock_date:
        mock_date.today.return_value = today
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        result = get_daily_budget_info(balance=-700.0, salary_day=25, advance_day=None)
    assert result['daily'] == pytest.approx(-100.0)


def test_get_daily_budget_picks_nearest():
    """Берётся ближайшая из двух дат."""
    from app import get_daily_budget_info
    today = date(2026, 4, 18)
    with patch('app.date') as mock_date:
        mock_date.today.return_value = today
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        result = get_daily_budget_info(balance=700.0, salary_day=10, advance_day=25)
    assert result['days_left'] == 7
    assert result['payment_type'] == 'аванса'


def _register_and_login(client):
    client.post('/register', data={
        'username': 'testuser',
        'email': 'test@example.com',
        'password': 'secret123',
        'confirm': 'secret123',
    })
    client.post('/login', data={'username': 'testuser', 'password': 'secret123'})


def test_payment_days_save(client):
    """POST /api/payment-days сохраняет дни выплат."""
    _register_and_login(client)
    resp = client.post('/api/payment-days', data={'salary_day': '25', 'advance_day': '10'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True

    from app import flask_app, db, User
    with flask_app.app_context():
        user = User.query.filter_by(username='testuser').first()
        assert user.salary_day == 25
        assert user.advance_day == 10


def test_payment_days_invalid(client):
    """Значения вне диапазона 1-31 отклоняются."""
    _register_and_login(client)
    resp = client.post('/api/payment-days', data={'salary_day': '99', 'advance_day': '0'})
    assert resp.status_code == 400


def test_payment_days_partial(client):
    """Можно передать только одно поле."""
    _register_and_login(client)
    resp = client.post('/api/payment-days', data={'salary_day': '25'})
    assert resp.status_code == 200
    from app import flask_app, User
    with flask_app.app_context():
        user = User.query.filter_by(username='testuser').first()
        assert user.salary_day == 25
        assert user.advance_day is None


def test_payment_days_requires_login(client):
    """Без авторизации — редирект на /login."""
    resp = client.post('/api/payment-days', data={'salary_day': '25'})
    assert resp.status_code in (302, 401)
