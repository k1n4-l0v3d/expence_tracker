import pytest
from datetime import date
import calendar
from app import app as flask_app, db, User, Category, Expense, Income, SavingsAccount


def _make_user():
    u = User(username='quser', email='q@example.com')
    u.set_password('pass1234')
    db.session.add(u)
    db.session.flush()
    return u


def _make_cat(user_id, name='Еда'):
    c = Category(name=name, color='#ff0000', icon='bi-bag', user_id=user_id)
    db.session.add(c)
    db.session.flush()
    return c


def _make_expense(user_id, cat_id, amount, expense_date, description=None):
    e = Expense(
        user_id=user_id, category_id=cat_id,
        amount=amount, expense_date=expense_date,
        is_planned=True, is_spent=True,
        description=description,
    )
    db.session.add(e)
    db.session.flush()
    return e


# ── Tests ───────────────────────────────────────────────────────────

def test_category_month_query():
    """Message with category + month returns QUERY DATA with that category's sum."""
    from app import _extract_query_data
    today = date.today()
    with flask_app.app_context():
        u = _make_user()
        cat = _make_cat(u.id, 'Еда')
        _make_expense(u.id, cat.id, 1500, date(today.year, 4, 10))
        _make_expense(u.id, cat.id, 2000, date(today.year, 4, 20))
        db.session.commit()

        cats = Category.query.filter_by(user_id=u.id).all()
        result = _extract_query_data('сколько потратил на еду в апреле', u.id, cats)

    assert 'QUERY DATA' in result
    assert 'Еда' in result
    assert '₽' in result
    assert '3500' in result or '3 500' in result


def test_monthly_summary_query():
    """Message with month only returns summary with income/expenses."""
    from app import _extract_query_data
    today = date.today()
    with flask_app.app_context():
        u = _make_user()
        cat = _make_cat(u.id, 'Транспорт')
        _make_expense(u.id, cat.id, 800, date(today.year, 4, 5))
        db.session.commit()

        cats = Category.query.filter_by(user_id=u.id).all()
        result = _extract_query_data('сколько всего потратил в апреле', u.id, cats)

    assert 'QUERY DATA' in result
    assert 'доходы' in result
    assert 'расходы' in result


def test_recent_query_default_10():
    """'покажи последние траты' returns up to 10 expenses."""
    from app import _extract_query_data
    today = date.today()
    with flask_app.app_context():
        u = _make_user()
        cat = _make_cat(u.id, 'Разное')
        for i in range(12):
            _make_expense(u.id, cat.id, 100 + i, today, description=f'item{i}')
        db.session.commit()

        cats = Category.query.filter_by(user_id=u.id).all()
        result = _extract_query_data('покажи последние траты', u.id, cats)

    assert 'QUERY DATA' in result
    assert result.count('ID:') == 10


def test_recent_query_custom_n():
    """'последние 5 расходов' returns exactly 5 expense lines."""
    from app import _extract_query_data
    today = date.today()
    with flask_app.app_context():
        u = _make_user()
        cat = _make_cat(u.id, 'Разное')
        for i in range(8):
            _make_expense(u.id, cat.id, 200 + i, today, description=f'x{i}')
        db.session.commit()

        cats = Category.query.filter_by(user_id=u.id).all()
        result = _extract_query_data('последние 5 расходов', u.id, cats)

    assert result.count('ID:') == 5


def test_comparison_query_two_months():
    """Message with two month names returns comparison block."""
    from app import _extract_query_data
    today = date.today()
    with flask_app.app_context():
        u = _make_user()
        cat = _make_cat(u.id, 'Кафе')
        _make_expense(u.id, cat.id, 3000, date(today.year, 3, 15))
        _make_expense(u.id, cat.id, 4000, date(today.year, 4, 15))
        db.session.commit()

        cats = Category.query.filter_by(user_id=u.id).all()
        result = _extract_query_data('сравни март и апрель', u.id, cats)

    assert 'QUERY DATA' in result
    assert 'март' in result.lower() or 'Март' in result
    assert 'апрель' in result.lower() or 'Апрель' in result
    assert 'Изменение' in result


def test_savings_query():
    """Message about savings returns account balances."""
    from app import _extract_query_data
    with flask_app.app_context():
        u = _make_user()
        acc = SavingsAccount(
            user_id=u.id, name='Отпуск',
            color='#0d6efd', icon='bi-piggy-bank',
            target_amount=100000, is_active=True,
        )
        db.session.add(acc)
        db.session.commit()

        cats = Category.query.filter_by(user_id=u.id).all()
        result = _extract_query_data('сколько на накоплениях', u.id, cats)

    assert 'QUERY DATA' in result
    assert 'Отпуск' in result
    assert '₽' in result


def test_no_query_on_write_message():
    """'добавь расход 500 еда' returns empty string — no query injection."""
    from app import _extract_query_data
    with flask_app.app_context():
        u = _make_user()
        cat = _make_cat(u.id, 'Еда')
        db.session.commit()
        cats = Category.query.filter_by(user_id=u.id).all()
        result = _extract_query_data('добавь расход 500 еда', u.id, cats)

    assert result == ''


def test_no_query_on_greeting():
    """'привет' returns empty string."""
    from app import _extract_query_data
    with flask_app.app_context():
        u = _make_user()
        db.session.commit()
        result = _extract_query_data('привет', u.id, [])

    assert result == ''
