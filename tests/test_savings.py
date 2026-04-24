import datetime
import pytest
from app import app as flask_app, db, User, SavingsAccount


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
