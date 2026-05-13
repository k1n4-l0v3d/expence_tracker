import datetime
import pytest
from app import app as flask_app, db, User, Expense, Income, Category
from sqlalchemy import extract as db_extract


@pytest.fixture
def user_client(client):
    with flask_app.app_context():
        u = User(username='copyuser', email='copy@example.com', role='user')
        u.set_password('pass123')
        db.session.add(u)
        db.session.commit()
    client.post('/login', data={'username': 'copyuser', 'password': 'pass123', 'website': ''})
    with flask_app.app_context():
        cat = Category(name='CopyCat', color='#334455')
        db.session.add(cat)
        db.session.commit()
        uid = User.query.filter_by(username='copyuser').first().id
        cat_id = cat.id
    return client, uid, cat_id


def test_can_copy_shown_when_current_empty_prev_has_data(user_client):
    """Dashboard shows copy button when current month empty, previous has planned expense."""
    client, uid, cat_id = user_client
    with flask_app.app_context():
        exp = Expense(user_id=uid, category_id=cat_id, amount=100,
                      expense_date=datetime.date(2026, 3, 15),
                      is_planned=True, is_spent=False)
        db.session.add(exp)
        db.session.commit()
    resp = client.get('/?year=2026&month=4')
    assert b'copy-from-previous' in resp.data


def test_can_copy_hidden_when_current_not_empty(user_client):
    """Dashboard hides copy button when current month already has expenses."""
    client, uid, cat_id = user_client
    with flask_app.app_context():
        db.session.add(Expense(user_id=uid, category_id=cat_id, amount=50,
                               expense_date=datetime.date(2026, 3, 10),
                               is_planned=True))
        db.session.add(Expense(user_id=uid, category_id=cat_id, amount=200,
                               expense_date=datetime.date(2026, 4, 5),
                               is_planned=True))
        db.session.commit()
    resp = client.get('/?year=2026&month=4')
    assert b'copy-from-previous' not in resp.data


def test_can_copy_hidden_when_prev_has_no_planned(user_client):
    """Dashboard hides copy button when previous month has no planned expenses and no income."""
    client, uid, cat_id = user_client
    with flask_app.app_context():
        db.session.add(Expense(user_id=uid, category_id=cat_id, amount=50,
                               expense_date=datetime.date(2026, 3, 10),
                               is_planned=False))
        db.session.commit()
    resp = client.get('/?year=2026&month=4')
    assert b'copy-from-previous' not in resp.data


def test_copy_creates_expenses_and_income(user_client):
    """POST /copy-from-previous copies planned expenses and income into target month."""
    client, uid, cat_id = user_client
    with flask_app.app_context():
        db.session.add(Expense(user_id=uid, category_id=cat_id, amount=500,
                               expense_date=datetime.date(2026, 3, 15),
                               description='Курс', is_planned=True, is_spent=True))
        db.session.add(Expense(user_id=uid, category_id=cat_id, amount=200,
                               expense_date=datetime.date(2026, 3, 20),
                               is_planned=False))  # should NOT be copied
        db.session.add(Income(user_id=uid, source='Зарплата', amount=50000,
                              income_date=datetime.date(2026, 3, 10)))
        db.session.commit()

    resp = client.post('/copy-from-previous',
                       data={'year': '2026', 'month': '4'},
                       follow_redirects=True)
    assert resp.status_code == 200

    with flask_app.app_context():
        copied_exp = Expense.query.filter(
            Expense.user_id == uid,
            db_extract('year',  Expense.expense_date) == 2026,
            db_extract('month', Expense.expense_date) == 4,
        ).all()
        copied_inc = Income.query.filter(
            Income.user_id == uid,
            db_extract('year',  Income.income_date) == 2026,
            db_extract('month', Income.income_date) == 4,
        ).all()

    assert len(copied_exp) == 1
    assert copied_exp[0].is_spent is False
    assert copied_exp[0].expense_date == datetime.date(2026, 4, 15)
    assert float(copied_exp[0].amount) == 500.0
    assert copied_exp[0].description == 'Курс'

    assert len(copied_inc) == 1
    assert copied_inc[0].income_date == datetime.date(2026, 4, 10)
    assert float(copied_inc[0].amount) == 50000.0


def test_copy_day_capped_to_last_day_of_month(user_client):
    """Day 31 in March becomes day 30 in April (last day capped)."""
    client, uid, cat_id = user_client
    with flask_app.app_context():
        db.session.add(Expense(user_id=uid, category_id=cat_id, amount=100,
                               expense_date=datetime.date(2026, 3, 31),
                               is_planned=True))
        db.session.commit()

    client.post('/copy-from-previous',
                data={'year': '2026', 'month': '4'},
                follow_redirects=True)

    with flask_app.app_context():
        exp = Expense.query.filter(
            Expense.user_id == uid,
            db_extract('year',  Expense.expense_date) == 2026,
            db_extract('month', Expense.expense_date) == 4,
        ).first()
    assert exp.expense_date == datetime.date(2026, 4, 30)


def test_copy_works_across_year_boundary(user_client):
    """Copying into January correctly uses December of previous year as source."""
    client, uid, cat_id = user_client
    with flask_app.app_context():
        db.session.add(Expense(user_id=uid, category_id=cat_id, amount=300,
                               expense_date=datetime.date(2025, 12, 5),
                               is_planned=True))
        db.session.commit()

    client.post('/copy-from-previous',
                data={'year': '2026', 'month': '1'},
                follow_redirects=True)

    with flask_app.app_context():
        exp = Expense.query.filter(
            Expense.user_id == uid,
            db_extract('year',  Expense.expense_date) == 2026,
            db_extract('month', Expense.expense_date) == 1,
        ).first()
    assert exp is not None
    assert exp.expense_date == datetime.date(2026, 1, 5)
