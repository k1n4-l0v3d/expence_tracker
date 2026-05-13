import io
import datetime
import pytest
from app import app as flask_app, db, User, Expense, Category, ExpenseAttachment


ALLOWED_MIME = 'image/jpeg'
PDF_MIME     = 'application/pdf'
MAX_SIZE     = 10 * 1024 * 1024  # 10 MB

TINY_JPEG = (
    b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
    b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
    b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
    b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\x1e'
    b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00'
    b'\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00'
    b'\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b'
    b'\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfb\xff\xd9'
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def user_and_client(client):
    """Register + login a user, return (client, user_id)."""
    with flask_app.app_context():
        u = User(username='testuser', email='test@example.com', role='user')
        u.set_password('pass123')
        db.session.add(u)
        db.session.commit()
        uid = u.id
    client.post('/login', data={'username': 'testuser', 'password': 'pass123', 'website': ''})
    return client, uid


@pytest.fixture
def expense_and_client(user_and_client):
    """Create an expense belonging to the logged-in user."""
    client, uid = user_and_client
    with flask_app.app_context():
        cat = Category(name='Test', color='#aaaaaa')
        db.session.add(cat)
        db.session.flush()
        exp = Expense(
            user_id=uid, category_id=cat.id,
            amount=100, expense_date=datetime.date.today()
        )
        db.session.add(exp)
        db.session.commit()
        exp_id = exp.id
    return client, uid, exp_id


@pytest.fixture
def attachment_fixture(expense_and_client):
    """Create an attachment record directly in DB."""
    client, uid, exp_id = expense_and_client
    with flask_app.app_context():
        att = ExpenseAttachment(
            expense_id=exp_id,
            filename='test.jpg',
            mime_type='image/jpeg',
            data=b'fakeimagecontent',
            size=16,
        )
        db.session.add(att)
        db.session.commit()
        att_id = att.id
    return client, uid, exp_id, att_id


# ─── Model tests ─────────────────────────────────────────────────────────────

def test_attachment_model_creates_and_links(expense_and_client):
    client, uid, exp_id = expense_and_client
    with flask_app.app_context():
        att = ExpenseAttachment(
            expense_id=exp_id, filename='receipt.jpg',
            mime_type='image/jpeg', data=b'abc', size=3,
        )
        db.session.add(att)
        db.session.commit()
        fetched = ExpenseAttachment.query.get(att.id)
        assert fetched.expense_id == exp_id
        assert fetched.filename == 'receipt.jpg'
        assert fetched.data == b'abc'


def test_attachment_deleted_with_expense(expense_and_client):
    client, uid, exp_id = expense_and_client
    with flask_app.app_context():
        att = ExpenseAttachment(
            expense_id=exp_id, filename='r.jpg',
            mime_type='image/jpeg', data=b'x', size=1,
        )
        db.session.add(att)
        db.session.commit()
        att_id = att.id
        exp = Expense.query.get(exp_id)
        db.session.delete(exp)
        db.session.commit()
        assert ExpenseAttachment.query.get(att_id) is None


# ─── Serve route tests ───────────────────────────────────────────────────────

def test_serve_attachment_returns_content(attachment_fixture):
    client, uid, exp_id, att_id = attachment_fixture
    resp = client.get(f'/attachments/{att_id}')
    assert resp.status_code == 200
    assert resp.data == b'fakeimagecontent'
    assert resp.content_type == 'image/jpeg'


def test_serve_attachment_requires_login(attachment_fixture):
    _, uid, exp_id, att_id = attachment_fixture
    fresh = flask_app.test_client()
    resp = fresh.get(f'/attachments/{att_id}')
    assert resp.status_code == 302  # redirect to login


def test_serve_attachment_forbidden_for_other_user(attachment_fixture):
    client, uid, exp_id, att_id = attachment_fixture
    with flask_app.app_context():
        u2 = User(username='other', email='other@example.com', role='user')
        u2.set_password('pass123')
        db.session.add(u2)
        db.session.commit()
    other_client = flask_app.test_client()
    other_client.post('/login', data={'username': 'other', 'password': 'pass123', 'website': ''})
    resp = other_client.get(f'/attachments/{att_id}')
    assert resp.status_code == 403


def test_serve_attachment_404_for_missing(user_and_client):
    client, uid = user_and_client
    resp = client.get('/attachments/99999')
    assert resp.status_code == 404


# ─── Upload route tests ──────────────────────────────────────────────────────

def _upload(client, exp_id, data=None, filename='r.jpg', mime='image/jpeg'):
    if data is None:
        data = TINY_JPEG
    return client.post(
        f'/expenses/{exp_id}/attachments',
        data={'file': (io.BytesIO(data), filename, mime)},
        content_type='multipart/form-data',
    )


def test_upload_attachment_success(expense_and_client):
    client, uid, exp_id = expense_and_client
    resp = _upload(client, exp_id)
    assert resp.status_code == 201
    json_data = resp.get_json()
    assert 'id' in json_data
    assert json_data['filename'] == 'r.jpg'
    assert json_data['mime_type'] == 'image/jpeg'
    with flask_app.app_context():
        att = ExpenseAttachment.query.get(json_data['id'])
        assert att is not None
        assert att.data == TINY_JPEG


def test_upload_rejected_wrong_mime(expense_and_client):
    client, uid, exp_id = expense_and_client
    resp = _upload(client, exp_id, data=b'notanimage', filename='bad.exe', mime='application/octet-stream')
    assert resp.status_code == 415


def test_upload_rejected_too_large(expense_and_client):
    client, uid, exp_id = expense_and_client
    big = b'x' * (10 * 1024 * 1024 + 1)
    resp = _upload(client, exp_id, data=big, filename='big.jpg', mime='image/jpeg')
    assert resp.status_code == 413


def test_upload_rejected_too_many(expense_and_client):
    client, uid, exp_id = expense_and_client
    with flask_app.app_context():
        for i in range(10):
            db.session.add(ExpenseAttachment(
                expense_id=exp_id, filename=f'{i}.jpg',
                mime_type='image/jpeg', data=b'x', size=1,
            ))
        db.session.commit()
    resp = _upload(client, exp_id)
    assert resp.status_code == 409


def test_upload_forbidden_other_user_expense(expense_and_client):
    client, uid, exp_id = expense_and_client
    with flask_app.app_context():
        u2 = User(username='other2', email='other2@example.com', role='user')
        u2.set_password('pass123')
        db.session.add(u2)
        db.session.commit()
    other = flask_app.test_client()
    other.post('/login', data={'username': 'other2', 'password': 'pass123', 'website': ''})
    resp = _upload(other, exp_id)
    assert resp.status_code == 403


# ─── Delete route tests ──────────────────────────────────────────────────────

def test_delete_attachment_success(attachment_fixture):
    client, uid, exp_id, att_id = attachment_fixture
    resp = client.delete(f'/attachments/{att_id}')
    assert resp.status_code == 200
    assert resp.get_json()['ok'] is True
    with flask_app.app_context():
        assert ExpenseAttachment.query.get(att_id) is None


def test_delete_attachment_forbidden(attachment_fixture):
    client, uid, exp_id, att_id = attachment_fixture
    with flask_app.app_context():
        u2 = User(username='other3', email='other3@example.com', role='user')
        u2.set_password('pass123')
        db.session.add(u2)
        db.session.commit()
    other = flask_app.test_client()
    other.post('/login', data={'username': 'other3', 'password': 'pass123', 'website': ''})
    resp = other.delete(f'/attachments/{att_id}')
    assert resp.status_code == 403
    with flask_app.app_context():
        assert ExpenseAttachment.query.get(att_id) is not None


# ─── expense_add multipart test ──────────────────────────────────────────────

def test_expense_add_with_file_creates_attachment(user_and_client):
    client, uid = user_and_client
    with flask_app.app_context():
        cat = Category(name='Food', color='#00ff00')
        db.session.add(cat)
        db.session.commit()
        cat_id = cat.id

    resp = client.post('/expenses/add', data={
        'category_id': cat_id,
        'amount': '250',
        'expense_date': datetime.date.today().strftime('%Y-%m-%d'),
        'description': 'test',
        'attachments': (io.BytesIO(TINY_JPEG), 'receipt.jpg', 'image/jpeg'),
    }, content_type='multipart/form-data', follow_redirects=True)
    assert resp.status_code == 200
    with flask_app.app_context():
        exp = Expense.query.filter_by(user_id=uid).first()
        assert exp is not None
        att = ExpenseAttachment.query.filter_by(expense_id=exp.id).first()
        assert att is not None
        assert att.filename == 'receipt.jpg'
