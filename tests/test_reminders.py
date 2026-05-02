import datetime
import pytest
from app import app as flask_app, db, User, Expense, Category


@pytest.fixture
def logged_in(client):
    with flask_app.app_context():
        u = User(username='remuser', email='rem@example.com', role='user')
        u.set_password('pass123')
        db.session.add(u)
        db.session.commit()
    client.post('/login', data={'username': 'remuser', 'password': 'pass123', 'website': ''})
    with flask_app.app_context():
        cat = Category(name='RemCat', color='#aabbcc')
        db.session.add(cat)
        db.session.commit()
        cat_id = cat.id
        uid = User.query.filter_by(username='remuser').first().id
    return client, uid, cat_id


def test_reminder_shown_for_tomorrow_unspent(logged_in):
    """Dashboard HTML contains reminder toast for unspent expense due tomorrow."""
    client, uid, cat_id = logged_in
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    with flask_app.app_context():
        exp = Expense(user_id=uid, category_id=cat_id,
                      amount=500, expense_date=tomorrow,
                      description='Курс Python', is_spent=False)
        db.session.add(exp)
        db.session.commit()
        exp_id = exp.id
    resp = client.get('/')
    assert resp.status_code == 200
    assert f'reminder-toast-{exp_id}'.encode() in resp.data


def test_no_reminder_for_spent_expense(logged_in):
    """No toast when expense is already spent."""
    client, uid, cat_id = logged_in
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    with flask_app.app_context():
        exp = Expense(user_id=uid, category_id=cat_id,
                      amount=500, expense_date=tomorrow,
                      description='Уже оплачено', is_spent=True)
        db.session.add(exp)
        db.session.commit()
        exp_id = exp.id
    resp = client.get('/')
    assert f'reminder-toast-{exp_id}'.encode() not in resp.data


def test_no_reminder_for_today_expense(logged_in):
    """No toast for expense due today (not tomorrow)."""
    client, uid, cat_id = logged_in
    today = datetime.date.today()
    with flask_app.app_context():
        exp = Expense(user_id=uid, category_id=cat_id,
                      amount=300, expense_date=today,
                      description='Сегодня', is_spent=False)
        db.session.add(exp)
        db.session.commit()
        exp_id = exp.id
    resp = client.get('/')
    assert f'reminder-toast-{exp_id}'.encode() not in resp.data


def test_no_reminder_for_anonymous():
    """Anonymous user gets no reminder toasts."""
    with flask_app.test_client() as anon:
        resp = anon.get('/', follow_redirects=True)
        assert b'reminder-toast-' not in resp.data
