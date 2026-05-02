import datetime
import pytest
from app import (app as flask_app, db, User, SavingsAccount,
                 get_account_balance, Category, Expense, Income)


@pytest.fixture
def user_client(client):
    with flask_app.app_context():
        u = User(username='saver', email='saver@ex.com', role='user')
        u.set_password('pass')
        db.session.add(u)
        db.session.commit()
        uid = u.id
    client.post('/login', data={'username': 'saver', 'password': 'pass', 'website': ''})
    return client, uid


def test_savings_account_model_creation(user_client):
    """SavingsAccount can be created and persisted."""
    _, uid = user_client
    with flask_app.app_context():
        acc = SavingsAccount(
            user_id=uid,
            name='Отпуск',
            color='#3b82f6',
            target_amount=150000,
        )
        db.session.add(acc)
        db.session.commit()
        assert acc.id is not None
        assert acc.is_active is True
        assert float(acc.target_amount) == 150000.0
        assert acc.icon == 'bi-piggy-bank'


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def account(user_client):
    """Returns (client, uid, acc_id) with a fresh SavingsAccount."""
    client, uid = user_client
    with flask_app.app_context():
        acc = SavingsAccount(user_id=uid, name='Test', color='#000000')
        db.session.add(acc)
        db.session.commit()
        acc_id = acc.id
    return client, uid, acc_id


# ─── Balance tests ────────────────────────────────────────────────────────────

def test_balance_empty(account):
    _, uid, acc_id = account
    with flask_app.app_context():
        assert get_account_balance(acc_id) == 0.0


def test_balance_after_deposit(account):
    _, uid, acc_id = account
    with flask_app.app_context():
        cat = Category(name='Накопления', icon='bi-piggy-bank', color='#0d6efd')
        db.session.add(cat)
        db.session.commit()
        exp = Expense(
            user_id=uid, category_id=cat.id, savings_account_id=acc_id,
            amount=10000, expense_date=datetime.date.today(),
            is_spent=True, is_planned=False,
        )
        db.session.add(exp)
        db.session.commit()
        assert get_account_balance(acc_id) == 10000.0


def test_balance_after_deposit_and_withdraw(account):
    _, uid, acc_id = account
    with flask_app.app_context():
        cat = Category(name='Накопления', icon='bi-piggy-bank', color='#0d6efd')
        db.session.add(cat)
        db.session.commit()
        exp = Expense(
            user_id=uid, category_id=cat.id, savings_account_id=acc_id,
            amount=7000, expense_date=datetime.date.today(),
            is_spent=True, is_planned=False,
        )
        db.session.add(exp)
        db.session.commit()
        assert get_account_balance(acc_id) == 7000.0


# ─── CRUD route tests ─────────────────────────────────────────────────────────

def test_savings_list_empty(user_client):
    client, _ = user_client
    resp = client.get('/savings')
    assert resp.status_code == 200
    assert 'Накопительные счета' in resp.data.decode()


def test_savings_add_json(user_client):
    client, _ = user_client
    resp = client.post('/savings/add',
                       json={'name': 'Отпуск', 'color': '#3b82f6', 'target_amount': 50000},
                       content_type='application/json')
    assert resp.status_code == 201
    data = resp.get_json()
    assert data['name'] == 'Отпуск'


def test_savings_add_missing_name(user_client):
    client, _ = user_client
    resp = client.post('/savings/add',
                       json={'color': '#000000'},
                       content_type='application/json')
    assert resp.status_code == 400


def test_savings_delete_empty_account(user_client):
    client, uid = user_client
    with flask_app.app_context():
        acc = SavingsAccount(user_id=uid, name='ToDelete', color='#000000')
        db.session.add(acc)
        db.session.commit()
        acc_id = acc.id
    resp = client.delete(f'/savings/{acc_id}')
    assert resp.status_code == 200
    assert resp.get_json()['ok'] is True


def test_savings_delete_with_transactions_cascades(account):
    client, uid, acc_id = account
    with flask_app.app_context():
        cat = Category(name='Накопления', icon='bi-piggy-bank', color='#0d6efd')
        db.session.add(cat)
        db.session.commit()
        exp = Expense(
            user_id=uid, category_id=cat.id, savings_account_id=acc_id,
            amount=1000, expense_date=datetime.date.today(),
            is_spent=True, is_planned=False,
        )
        db.session.add(exp)
        db.session.commit()
    resp = client.delete(f'/savings/{acc_id}')
    assert resp.status_code == 200
    assert resp.get_json()['ok'] is True
    with flask_app.app_context():
        assert SavingsAccount.query.get(acc_id) is None
        assert Expense.query.filter_by(savings_account_id=acc_id).count() == 0


# ─── Deposit / withdraw tests ─────────────────────────────────────────────────

def test_deposit_creates_expense_and_updates_balance(account):
    client, uid, acc_id = account
    today = datetime.date.today().isoformat()
    resp = client.post(f'/savings/{acc_id}/deposit',
                       json={'amount': 20000, 'date': today, 'description': 'Первый взнос'},
                       content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True
    assert data['balance'] == 20000.0

    with flask_app.app_context():
        exp = Expense.query.filter_by(savings_account_id=acc_id).first()
        assert exp is not None
        assert float(exp.amount) == 20000.0
        assert exp.is_spent is True
        assert exp.is_planned is False


def test_withdraw_reduces_expense_amount(account):
    client, uid, acc_id = account
    today = datetime.date.today().isoformat()
    client.post(f'/savings/{acc_id}/deposit',
                json={'amount': 15000, 'date': today},
                content_type='application/json')
    resp = client.post(f'/savings/{acc_id}/withdraw',
                       json={'amount': 5000, 'date': today},
                       content_type='application/json')
    assert resp.status_code == 200
    assert resp.get_json()['balance'] == 10000.0

    with flask_app.app_context():
        exp = Expense.query.filter_by(savings_account_id=acc_id).first()
        assert exp is not None
        assert float(exp.amount) == 10000.0
        # No income record created
        inc = Income.query.filter_by(savings_account_id=acc_id).first()
        assert inc is None


def test_withdraw_full_amount_deletes_expense(account):
    client, uid, acc_id = account
    today = datetime.date.today().isoformat()
    client.post(f'/savings/{acc_id}/deposit',
                json={'amount': 10000, 'date': today},
                content_type='application/json')
    resp = client.post(f'/savings/{acc_id}/withdraw',
                       json={'amount': 10000, 'date': today},
                       content_type='application/json')
    assert resp.status_code == 200
    assert resp.get_json()['balance'] == 0.0

    with flask_app.app_context():
        exp = Expense.query.filter_by(savings_account_id=acc_id).first()
        assert exp is None


def test_withdraw_overdraft_rejected(account):
    client, uid, acc_id = account
    today = datetime.date.today().isoformat()
    client.post(f'/savings/{acc_id}/deposit',
                json={'amount': 1000, 'date': today},
                content_type='application/json')
    resp = client.post(f'/savings/{acc_id}/withdraw',
                       json={'amount': 9999, 'date': today},
                       content_type='application/json')
    assert resp.status_code == 400
    assert 'Недостаточно средств' in resp.get_json()['error']


def test_deposit_invalid_amount_rejected(account):
    client, uid, acc_id = account
    resp = client.post(f'/savings/{acc_id}/deposit',
                       json={'amount': -100, 'date': '2026-04-24'},
                       content_type='application/json')
    assert resp.status_code == 400


def test_deposit_other_user_returns_404(account):
    client, uid, acc_id = account
    with flask_app.app_context():
        u2 = User(username='other2', email='other2@ex.com', role='user')
        u2.set_password('pass')
        db.session.add(u2)
        db.session.commit()
    other = flask_app.test_client()
    other.post('/login', data={'username': 'other2', 'password': 'pass', 'website': ''})
    resp = other.post(f'/savings/{acc_id}/deposit',
                      json={'amount': 100, 'date': '2026-04-24'},
                      content_type='application/json')
    assert resp.status_code == 404
