import pytest
from datetime import date
from app import app as flask_app, db, User, Category, Expense, MonthlyBudget


def _register_and_login(client, username='testuser', password='pass1234'):
    client.post('/register', data={
        'username': username, 'email': f'{username}@example.com',
        'password': password, 'confirm': password,
    }, follow_redirects=True)
    client.post('/login', data={'login': username, 'password': password},
                follow_redirects=True)


def test_alert_map_warning_shown_in_index(client):
    """When spending >= alert threshold, index returns 200 and alert_map contains 'warning'."""
    _register_and_login(client)
    today = date.today()

    with flask_app.app_context():
        user = User.query.filter_by(username='testuser').first()
        user.budget_alert_pct = 80
        cat = Category(name='Cafe', color='#aabbcc', icon='bi-cup', user_id=user.id)
        db.session.add(cat)
        db.session.flush()

        # Budget: 1000, spending: 850 (85%) → warning
        budget = MonthlyBudget(
            user_id=user.id, category_id=cat.id,
            year=today.year, month=today.month, amount=1000
        )
        exp = Expense(
            user_id=user.id, category_id=cat.id,
            amount=850, description='coffee',
            expense_date=today, is_planned=True, is_spent=True,
        )
        db.session.add_all([budget, exp])
        db.session.commit()

    resp = client.get(f'/?year={today.year}&month={today.month}')
    assert resp.status_code == 200
    # ⚠️ icon or its title text should appear in rendered HTML
    assert b'85%' in resp.data or b'alert-warning-row' in resp.data


def test_alert_map_exceeded_shown_in_index(client):
    """When spending > budget, index should flag as exceeded."""
    _register_and_login(client)
    today = date.today()

    with flask_app.app_context():
        user = User.query.filter_by(username='testuser').first()
        cat = Category(name='Games', color='#ff0000', icon='bi-joystick', user_id=user.id)
        db.session.add(cat)
        db.session.flush()

        budget = MonthlyBudget(
            user_id=user.id, category_id=cat.id,
            year=today.year, month=today.month, amount=500
        )
        exp = Expense(
            user_id=user.id, category_id=cat.id,
            amount=600, description='game',
            expense_date=today, is_planned=True, is_spent=True,
        )
        db.session.add_all([budget, exp])
        db.session.commit()

    resp = client.get(f'/?year={today.year}&month={today.month}')
    assert resp.status_code == 200
    assert b'alert-exceeded-row' in resp.data or 'превышен'.encode() in resp.data


def test_inject_budget_alerts_returns_alerts(client):
    """inject_budget_alerts context processor injects budget_alerts into every page."""
    _register_and_login(client)
    today = date.today()

    with flask_app.app_context():
        user = User.query.filter_by(username='testuser').first()
        user.budget_alert_pct = 70
        cat = Category(name='Transport', color='#00aaff', icon='bi-bus', user_id=user.id)
        db.session.add(cat)
        db.session.flush()

        budget = MonthlyBudget(
            user_id=user.id, category_id=cat.id,
            year=today.year, month=today.month, amount=1000
        )
        exp = Expense(
            user_id=user.id, category_id=cat.id,
            amount=750, description='metro',
            expense_date=today, is_planned=True, is_spent=True,
        )
        db.session.add_all([budget, exp])
        db.session.commit()

    # budget page also uses base.html → context processor fires
    resp = client.get('/budget')
    assert resp.status_code == 200
    assert b'budget-alert-toast' in resp.data


def test_profile_budget_alert_pct_saves(client):
    """POST /profile/budget-alert-pct saves valid value and redirects to profile."""
    _register_and_login(client)

    resp = client.post('/profile/budget-alert-pct',
                       data={'budget_alert_pct': '65'},
                       follow_redirects=True)
    assert resp.status_code == 200

    with flask_app.app_context():
        user = User.query.filter_by(username='testuser').first()
        assert user.budget_alert_pct == 65


def test_profile_budget_alert_pct_rejects_invalid(client):
    """POST /profile/budget-alert-pct rejects values outside 1–100."""
    _register_and_login(client)

    client.post('/profile/budget-alert-pct',
                data={'budget_alert_pct': '150'},
                follow_redirects=True)

    with flask_app.app_context():
        user = User.query.filter_by(username='testuser').first()
        assert user.budget_alert_pct == 80  # unchanged default
