import os
import pathlib

_DB_PATH = pathlib.Path(__file__).parent.parent / "instance" / "test_expense.db"

# Must be set BEFORE importing app — load_dotenv() does not override existing env vars
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
os.environ["SECRET_KEY"] = "test-secret-key-for-tests-only"

import pytest
from app import app as flask_app, db


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create all tables once per test session, drop and delete file after."""
    flask_app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
    })
    with flask_app.app_context():
        db.create_all()
    yield
    with flask_app.app_context():
        db.drop_all()
    _DB_PATH.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def clean_db():
    """Delete all rows between tests."""
    yield
    with flask_app.app_context():
        from app import User, Expense, Income, MonthlyBudget, Category, ExpenseAttachment
        db.session.query(ExpenseAttachment).delete()
        db.session.query(MonthlyBudget).delete()
        db.session.query(Expense).delete()
        db.session.query(Income).delete()
        db.session.query(Category).delete()
        db.session.query(User).delete()
        db.session.commit()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear IP counters between tests."""
    from app import rate_limiter
    rate_limiter._data.clear()
    yield
    rate_limiter._data.clear()


@pytest.fixture
def client():
    return flask_app.test_client()
