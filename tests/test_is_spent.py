import datetime
import pytest
from app import app as flask_app, db, User, Expense, Category
from app import get_monthly_summary


@pytest.fixture
def user_and_client(client):
    with flask_app.app_context():
        u = User(username='spentuser', email='spent@example.com', role='user')
        u.set_password('pass123')
        db.session.add(u)
        db.session.commit()
        uid = u.id
    client.post('/login', data={'username': 'spentuser', 'password': 'pass123', 'website': ''})
    return client, uid


@pytest.fixture
def category_and_user(user_and_client):
    client, uid = user_and_client
    with flask_app.app_context():
        cat = Category(name='SpentCat', color='#123456')
        db.session.add(cat)
        db.session.commit()
        cat_id = cat.id
    return client, uid, cat_id


def test_is_spent_defaults_true(category_and_user):
    """New expense has is_spent=True by default."""
    client, uid, cat_id = category_and_user
    with flask_app.app_context():
        exp = Expense(user_id=uid, category_id=cat_id,
                      amount=100, expense_date=datetime.date.today())
        db.session.add(exp)
        db.session.commit()
        assert exp.is_spent is True


def test_unspent_excluded_from_summary(category_and_user):
    """Expense with is_spent=False is NOT counted in get_monthly_summary."""
    client, uid, cat_id = category_and_user
    today = datetime.date.today()
    with flask_app.app_context():
        exp = Expense(user_id=uid, category_id=cat_id,
                      amount=500, expense_date=today, is_spent=False)
        db.session.add(exp)
        db.session.commit()
        rows = get_monthly_summary(uid, today.year, today.month)
        total = sum(float(r.total) for r in rows)
        assert total == 0.0


def test_spent_included_in_summary(category_and_user):
    """Expense with is_spent=True IS counted in get_monthly_summary."""
    client, uid, cat_id = category_and_user
    today = datetime.date.today()
    with flask_app.app_context():
        exp = Expense(user_id=uid, category_id=cat_id,
                      amount=300, expense_date=today, is_spent=True)
        db.session.add(exp)
        db.session.commit()
        rows = get_monthly_summary(uid, today.year, today.month)
        total = sum(float(r.total) for r in rows)
        assert total == 300.0


def test_expense_add_is_spent_false(category_and_user):
    """POST /expenses/add with is_spent unchecked creates unspent expense."""
    client, uid, cat_id = category_and_user
    resp = client.post('/expenses/add', data={
        'category_id': cat_id,
        'amount': '250',
        'expense_date': datetime.date.today().strftime('%Y-%m-%d'),
        'description': 'test',
        # is_spent NOT sent → unchecked
    }, content_type='multipart/form-data', follow_redirects=True)
    assert resp.status_code == 200
    with flask_app.app_context():
        exp = Expense.query.filter_by(user_id=uid).first()
        assert exp is not None
        assert exp.is_spent is False


def test_expense_add_is_spent_true(category_and_user):
    """POST /expenses/add with is_spent checked creates spent expense."""
    client, uid, cat_id = category_and_user
    resp = client.post('/expenses/add', data={
        'category_id': cat_id,
        'amount': '250',
        'expense_date': datetime.date.today().strftime('%Y-%m-%d'),
        'description': 'test',
        'is_spent': 'on',
    }, content_type='multipart/form-data', follow_redirects=True)
    assert resp.status_code == 200
    with flask_app.app_context():
        exp = Expense.query.filter_by(user_id=uid).first()
        assert exp.is_spent is True


def test_toggle_spent(category_and_user):
    """POST /expenses/<id>/toggle-spent flips is_spent and returns JSON."""
    client, uid, cat_id = category_and_user
    with flask_app.app_context():
        exp = Expense(user_id=uid, category_id=cat_id,
                      amount=100, expense_date=datetime.date.today(), is_spent=True)
        db.session.add(exp)
        db.session.commit()
        exp_id = exp.id

    resp = client.post(f'/expenses/{exp_id}/toggle-spent',
                       headers={'X-CSRFToken': ''})
    assert resp.status_code == 200
    assert resp.get_json()['is_spent'] is False

    resp2 = client.post(f'/expenses/{exp_id}/toggle-spent',
                        headers={'X-CSRFToken': ''})
    assert resp2.get_json()['is_spent'] is True


def test_toggle_spent_forbidden(category_and_user):
    """Other user cannot toggle."""
    client, uid, cat_id = category_and_user
    with flask_app.app_context():
        exp = Expense(user_id=uid, category_id=cat_id,
                      amount=100, expense_date=datetime.date.today())
        db.session.add(exp)
        db.session.commit()
        exp_id = exp.id

    with flask_app.app_context():
        u2 = User(username='other_spent', email='other_spent@example.com', role='user')
        u2.set_password('pass123')
        db.session.add(u2)
        db.session.commit()
    other = flask_app.test_client()
    other.post('/login', data={'username': 'other_spent', 'password': 'pass123', 'website': ''})
    resp = other.post(f'/expenses/{exp_id}/toggle-spent')
    assert resp.status_code == 403
