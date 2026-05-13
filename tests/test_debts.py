import pytest
from app import app as flask_app, db, Debt


def _register_and_login(client, username='debtuser', password='pass1234'):
    client.post('/register', data={
        'username': username, 'email': f'{username}@example.com',
        'password': password, 'confirm': password,
    }, follow_redirects=True)
    client.post('/login', data={'login': username, 'password': password},
                follow_redirects=True)


def test_debts_list_requires_auth(client):
    """GET /debts without login redirects."""
    resp = client.get('/debts', follow_redirects=False)
    assert resp.status_code == 302


def test_debt_add_owe(client):
    """POST /debts/add with direction=owe creates debt and flashes success."""
    _register_and_login(client)
    resp = client.post('/debts/add',
                       data={'person_name': 'Ваня', 'amount': '5000', 'direction': 'owe'},
                       follow_redirects=True)
    assert resp.status_code == 200
    assert 'Долг добавлен'.encode() in resp.data


def test_debt_add_owed(client):
    """POST /debts/add with direction=owed stores correct record."""
    _register_and_login(client)
    client.post('/debts/add',
                data={'person_name': 'Петя', 'amount': '3000', 'direction': 'owed'},
                follow_redirects=True)
    with flask_app.app_context():
        d = Debt.query.filter_by(person_name='Петя').first()
        assert d is not None
        assert d.direction == 'owed'
        assert float(d.amount) == 3000.0


def test_debt_toggle_paid(client):
    """POST /debts/<id>/toggle-paid flips is_paid from False to True."""
    _register_and_login(client)
    client.post('/debts/add',
                data={'person_name': 'Маша', 'amount': '1000', 'direction': 'owe'},
                follow_redirects=True)
    with flask_app.app_context():
        debt_id = Debt.query.filter_by(person_name='Маша').first().id
    client.post(f'/debts/{debt_id}/toggle-paid', follow_redirects=True)
    with flask_app.app_context():
        assert db.session.get(Debt, debt_id).is_paid is True


def test_debt_delete(client):
    """POST /debts/<id>/delete removes the record."""
    _register_and_login(client)
    client.post('/debts/add',
                data={'person_name': 'Саша', 'amount': '500', 'direction': 'owed'},
                follow_redirects=True)
    with flask_app.app_context():
        debt_id = Debt.query.filter_by(person_name='Саша').first().id
    client.post(f'/debts/{debt_id}/delete', follow_redirects=True)
    with flask_app.app_context():
        assert db.session.get(Debt, debt_id) is None


def test_dashboard_shows_debt_card(client):
    """Dashboard shows debt summary card when active debts exist."""
    _register_and_login(client)
    client.post('/debts/add',
                data={'person_name': 'Коля', 'amount': '2000', 'direction': 'owe'},
                follow_redirects=True)
    resp = client.get('/')
    assert resp.status_code == 200
    assert 'Долги'.encode() in resp.data
