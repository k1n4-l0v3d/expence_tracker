# Expense Attachments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to attach multiple images (JPG/PNG/WEBP) and PDFs (≤10 MB, ≤10 files) to expenses, stored as binary blobs in PostgreSQL.

**Architecture:** New `ExpenseAttachment` model stores binary data in DB. Three new routes handle serving, AJAX upload, and AJAX delete. The add-expense form uses synchronous multipart upload; the edit form uses AJAX for add/remove without page reload. List page shows a 📎 badge that opens a Bootstrap modal.

**Tech Stack:** Flask, SQLAlchemy `LargeBinary`, `flask.send_file`, `io.BytesIO`, Bootstrap 5 modal, `fetch` API.

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `app.py` | Modify | Add `ExpenseAttachment` model, `attachments` relationship on `Expense`, 3 new routes, update `expense_add()` for multipart, update `expenses_list()` for attachment counts |
| `templates/expenses/form.html` | Modify | Add attachments section (file input + existing thumbnails + AJAX JS) |
| `templates/expenses/list.html` | Modify | Add paperclip badge, attachments modal, JS to populate modal |
| `tests/conftest.py` | Modify | Add `ExpenseAttachment` to `clean_db` fixture |
| `tests/test_attachments.py` | Create | Full test coverage for all 3 routes |

---

## Task 1: ExpenseAttachment model + Expense relationship

**Files:**
- Modify: `app.py` (after `Expense` class, ~line 199)
- Modify: `app.py` `Expense` class (~line 185)
- Modify: `tests/conftest.py` (`clean_db` fixture)

- [ ] **Step 1: Add `ExpenseAttachment` model to `app.py` immediately after the `Expense` class**

Find the line `# ─── Декораторы ───` and insert before it:

```python
class ExpenseAttachment(db.Model):
    __tablename__ = 'expense_attachments'

    id         = db.Column(db.Integer, primary_key=True)
    expense_id = db.Column(db.Integer,
                           db.ForeignKey('expenses.id', ondelete='CASCADE'),
                           nullable=False)
    filename   = db.Column(db.String(255), nullable=False)
    mime_type  = db.Column(db.String(100), nullable=False)
    data       = db.Column(db.LargeBinary, nullable=False)
    size       = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
```

- [ ] **Step 2: Add `attachments` relationship to `Expense` class**

In the `Expense` class (after the `updated_at` column), add:

```python
    attachments = db.relationship('ExpenseAttachment', backref='expense',
                                  lazy=True, cascade='all, delete-orphan')
```

- [ ] **Step 3: Update `clean_db` fixture in `tests/conftest.py`**

Change the import line and add `ExpenseAttachment` deletion:

```python
# Old import line:
from app import User, Expense, Income, MonthlyBudget, Category
# New:
from app import User, Expense, Income, MonthlyBudget, Category, ExpenseAttachment

# Add before db.session.query(Expense).delete():
db.session.query(ExpenseAttachment).delete()
```

- [ ] **Step 4: Write failing test**

Create `tests/test_attachments.py`:

```python
import io
import pytest
from app import app as flask_app, db, User, Expense, Category, ExpenseAttachment


ALLOWED_MIME = 'image/jpeg'
PDF_MIME     = 'application/pdf'
MAX_SIZE     = 10 * 1024 * 1024  # 10 MB


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
            amount=100, expense_date=__import__('datetime').date.today()
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
```

- [ ] **Step 5: Run test — verify model tests pass**

```bash
python3 -m pytest tests/test_attachments.py::test_attachment_model_creates_and_links tests/test_attachments.py::test_attachment_deleted_with_expense -v
```

Expected: **2 passed**

- [ ] **Step 6: Run full suite — verify no regressions**

```bash
python3 -m pytest tests/ -q
```

Expected: **37 passed** (35 existing + 2 new)

- [ ] **Step 7: Commit**

```bash
git add app.py tests/conftest.py tests/test_attachments.py
git commit -m "feat: add ExpenseAttachment model with cascade delete"
```

---

## Task 2: GET /attachments/<id> — serve file from DB

**Files:**
- Modify: `app.py` (add route before `/budget` route, ~line 745)
- Modify: `tests/test_attachments.py` (add tests)

- [ ] **Step 1: Write failing tests for the serve route**

Append to `tests/test_attachments.py`:

```python
def test_serve_attachment_returns_content(attachment_fixture):
    client, uid, exp_id, att_id = attachment_fixture
    resp = client.get(f'/attachments/{att_id}')
    assert resp.status_code == 200
    assert resp.data == b'fakeimagecontent'
    assert resp.content_type == 'image/jpeg'

def test_serve_attachment_requires_login(client, attachment_fixture):
    # Use a fresh client (not logged in)
    _, uid, exp_id, att_id = attachment_fixture
    fresh = flask_app.test_client()
    resp = fresh.get(f'/attachments/{att_id}')
    assert resp.status_code == 302  # redirect to login

def test_serve_attachment_forbidden_for_other_user(attachment_fixture):
    client, uid, exp_id, att_id = attachment_fixture
    # Register second user
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
```

- [ ] **Step 2: Run — verify tests fail (route not defined)**

```bash
python3 -m pytest tests/test_attachments.py::test_serve_attachment_returns_content -v
```

Expected: **FAIL** with 404

- [ ] **Step 3: Add the route to `app.py` before the `/budget` route**

```python
@app.route('/attachments/<int:att_id>')
@login_required
def attachment_serve(att_id):
    att = ExpenseAttachment.query.get_or_404(att_id)
    if att.expense.user_id != current_user.id:
        return jsonify({'error': 'Доступ запрещён'}), 403
    return send_file(
        io.BytesIO(att.data),
        mimetype=att.mime_type,
        download_name=att.filename,
        as_attachment=False,
        max_age=3600,
    )
```

Make sure `import io` is at the top of `app.py` (add it if missing — check near the other stdlib imports).

Also ensure `send_file` is imported from flask:
```python
from flask import (Flask, render_template, request, redirect, url_for,
                   flash, jsonify, send_file)
```
(Check existing import and add `send_file` if not present.)

- [ ] **Step 4: Run serve tests — verify they pass**

```bash
python3 -m pytest tests/test_attachments.py -k "serve" -v
```

Expected: **4 passed**

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_attachments.py
git commit -m "feat: add GET /attachments/<id> route to serve binary from DB"
```

---

## Task 3: POST /expenses/<id>/attachments + DELETE /attachments/<id>

**Files:**
- Modify: `app.py` (add 2 routes after the serve route)
- Modify: `tests/test_attachments.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_attachments.py`:

```python
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


def _upload(client, exp_id, data=TINY_JPEG, filename='r.jpg', mime='image/jpeg'):
    return client.post(
        f'/expenses/{exp_id}/attachments',
        data={'file': (io.BytesIO(data), filename)},
        content_type='multipart/form-data',
        headers={'X-CSRFToken': 'ignored'},
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

def test_delete_attachment_success(attachment_fixture):
    client, uid, exp_id, att_id = attachment_fixture
    resp = client.delete(f'/attachments/{att_id}',
                         headers={'X-CSRFToken': 'ignored'})
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
    resp = other.delete(f'/attachments/{att_id}',
                        headers={'X-CSRFToken': 'ignored'})
    assert resp.status_code == 403
    with flask_app.app_context():
        assert ExpenseAttachment.query.get(att_id) is not None
```

- [ ] **Step 2: Run — verify all new tests fail**

```bash
python3 -m pytest tests/test_attachments.py -k "upload or delete_attachment" -v
```

Expected: all **FAIL** (routes not defined)

- [ ] **Step 3: Add upload + delete routes to `app.py` (after the serve route)**

```python
ALLOWED_MIME_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'application/pdf'}
MAX_ATTACHMENT_SIZE  = 10 * 1024 * 1024   # 10 MB
MAX_ATTACHMENTS      = 10


@app.route('/expenses/<int:exp_id>/attachments', methods=['POST'])
@login_required
@ban_check
def attachment_upload(exp_id):
    exp = Expense.query.filter_by(id=exp_id, user_id=current_user.id).first()
    if exp is None:
        return jsonify({'error': 'Расход не найден'}), 403

    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'Файл не передан'}), 400

    mime = f.mimetype or ''
    if mime not in ALLOWED_MIME_TYPES:
        return jsonify({'error': 'Недопустимый тип файла'}), 415

    data = f.read()
    if len(data) > MAX_ATTACHMENT_SIZE:
        return jsonify({'error': 'Файл слишком большой (макс. 10 МБ)'}), 413

    if ExpenseAttachment.query.filter_by(expense_id=exp_id).count() >= MAX_ATTACHMENTS:
        return jsonify({'error': 'Максимум 10 вложений на расход'}), 409

    att = ExpenseAttachment(
        expense_id=exp_id,
        filename=f.filename or 'file',
        mime_type=mime,
        data=data,
        size=len(data),
    )
    try:
        db.session.add(att)
        db.session.commit()
        return jsonify({'id': att.id, 'filename': att.filename,
                        'mime_type': att.mime_type, 'size': att.size}), 201
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Ошибка сохранения'}), 500


@app.route('/attachments/<int:att_id>', methods=['DELETE'])
@login_required
def attachment_delete(att_id):
    att = ExpenseAttachment.query.get_or_404(att_id)
    if att.expense.user_id != current_user.id:
        return jsonify({'error': 'Доступ запрещён'}), 403
    try:
        db.session.delete(att)
        db.session.commit()
        return jsonify({'ok': True})
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Ошибка удаления'}), 500
```

- [ ] **Step 4: Run upload/delete tests — verify they pass**

```bash
python3 -m pytest tests/test_attachments.py -k "upload or delete_attachment" -v
```

Expected: **8 passed**

- [ ] **Step 5: Run full suite — no regressions**

```bash
python3 -m pytest tests/ -q
```

Expected: **45 passed**

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_attachments.py
git commit -m "feat: add POST /expenses/<id>/attachments and DELETE /attachments/<id> routes"
```

---

## Task 4: Handle sync uploads in expense_add (add form)

**Files:**
- Modify: `app.py` — `expense_add()` function (~line 663)
- Modify: `tests/test_attachments.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_attachments.py`:

```python
def test_expense_add_with_file_creates_attachment(user_and_client):
    client, uid = user_and_client
    with flask_app.app_context():
        cat = Category(name='Food', color='#00ff00')
        db.session.add(cat)
        db.session.commit()
        cat_id = cat.id

    import datetime
    resp = client.post('/expenses/add', data={
        'category_id': cat_id,
        'amount': '250',
        'expense_date': datetime.date.today().strftime('%Y-%m-%d'),
        'description': 'test',
        'attachments': (io.BytesIO(TINY_JPEG), 'receipt.jpg'),
    }, content_type='multipart/form-data', follow_redirects=True)
    assert resp.status_code == 200
    with flask_app.app_context():
        exp = Expense.query.filter_by(user_id=uid).first()
        assert exp is not None
        att = ExpenseAttachment.query.filter_by(expense_id=exp.id).first()
        assert att is not None
        assert att.filename == 'receipt.jpg'
```

- [ ] **Step 2: Run — verify test fails**

```bash
python3 -m pytest tests/test_attachments.py::test_expense_add_with_file_creates_attachment -v
```

Expected: **FAIL** (attachment not created)

- [ ] **Step 3: Update `expense_add()` in `app.py`**

In the `expense_add()` function, after `db.session.commit()` (expense saved) and before `flash(...)`, add file processing. Change the POST block to:

```python
    if request.method == 'POST':
        try:
            exp = Expense(
                user_id      = current_user.id,
                category_id  = int(request.form['category_id']),
                amount       = float(request.form['amount']),
                description  = request.form.get('description', '').strip() or None,
                expense_date = datetime.strptime(request.form['expense_date'], '%Y-%m-%d').date(),
                is_planned   = request.form.get('is_planned') == 'on',
                notes        = request.form.get('notes', '').strip() or None,
            )
            db.session.add(exp)
            db.session.commit()

            # Process optional file attachments
            for f in request.files.getlist('attachments'):
                if not f or not f.filename:
                    continue
                mime = f.mimetype or ''
                if mime not in ALLOWED_MIME_TYPES:
                    continue
                data = f.read()
                if len(data) > MAX_ATTACHMENT_SIZE:
                    continue
                if ExpenseAttachment.query.filter_by(expense_id=exp.id).count() >= MAX_ATTACHMENTS:
                    break
                db.session.add(ExpenseAttachment(
                    expense_id=exp.id, filename=f.filename,
                    mime_type=mime, data=data, size=len(data),
                ))
            db.session.commit()

            flash('Расход добавлен!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка: {e}', 'danger')
```

- [ ] **Step 4: Run test — verify it passes**

```bash
python3 -m pytest tests/test_attachments.py::test_expense_add_with_file_creates_attachment -v
```

Expected: **PASS**

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest tests/ -q
```

Expected: **46 passed**

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_attachments.py
git commit -m "feat: handle file uploads in expense_add (sync multipart)"
```

---

## Task 5: Expense form template — attachments section

**Files:**
- Modify: `templates/expenses/form.html`

No new tests — this is template/JS only. Verify manually by running the app.

- [ ] **Step 1: Add `enctype` to the form tag**

Change:
```html
<form method="post">
```
To:
```html
<form method="post" enctype="multipart/form-data" id="expenseForm">
```

- [ ] **Step 2: Add attachments section before the `is_planned` checkbox block**

Insert after the Notes `<div class="mb-3">` block and before the `<div class="form-check mb-4">`:

```html
<div class="mb-3">
  <label class="form-label fw-semibold">
    <i class="bi bi-paperclip me-1"></i>Вложения
    <span class="text-muted fw-normal small">(фото, PDF · макс. 10 МБ)</span>
  </label>

  <!-- Existing attachments (edit mode only) -->
  {% if expense and expense.attachments %}
  <div class="d-flex gap-2 flex-wrap mb-2" id="existingAttachments">
    {% for att in expense.attachments %}
    <div class="position-relative" id="attThumb_{{ att.id }}" style="width:64px;height:64px">
      {% if att.mime_type.startswith('image/') %}
      <img src="{{ url_for('attachment_serve', att_id=att.id) }}"
           class="rounded border" style="width:64px;height:64px;object-fit:cover">
      {% else %}
      <div class="rounded border bg-body-secondary d-flex flex-column align-items-center justify-content-center"
           style="width:64px;height:64px">
        <i class="bi bi-file-earmark-pdf text-danger fs-4"></i>
        <span class="text-muted" style="font-size:9px;word-break:break-all;text-align:center;padding:0 2px">PDF</span>
      </div>
      {% endif %}
      <button type="button"
              class="btn btn-danger btn-sm position-absolute top-0 end-0 p-0 lh-1"
              style="width:18px;height:18px;font-size:10px;border-radius:50%"
              onclick="deleteAttachment({{ att.id }}, this)">✕</button>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  <!-- New file input -->
  <label class="d-flex align-items-center gap-2 border border-dashed rounded p-2 text-primary"
         style="cursor:pointer;border-style:dashed!important">
    <i class="bi bi-plus-circle"></i>
    <span class="small">Добавить фото или PDF</span>
    <input type="file" name="attachments" multiple
           accept="image/jpeg,image/png,image/webp,application/pdf"
           class="d-none" id="attachmentInput"
           {% if expense %}onchange="uploadFiles(this)"{% endif %}>
  </label>
  <div id="attachUploadError" class="text-danger small mt-1 d-none"></div>
</div>
```

- [ ] **Step 3: Add JavaScript for AJAX upload/delete (edit mode only)**

Append to the existing `{% block scripts %}` block in `form.html` (inside the `<script>` tag, after the existing category modal JS):

```javascript
// ── Attachments (edit mode) ──────────────────────────────────────────────────
{% if expense %}
const expenseId = {{ expense.id }};

async function uploadFiles(input) {
  const errEl = document.getElementById('attachUploadError');
  errEl.classList.add('d-none');
  for (const file of input.files) {
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await fetch(`/expenses/${expenseId}/attachments`, {
        method: 'POST',
        headers: {'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content},
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) { errEl.textContent = data.error || 'Ошибка загрузки'; errEl.classList.remove('d-none'); continue; }
      addThumb(data);
    } catch { errEl.textContent = 'Ошибка сети'; errEl.classList.remove('d-none'); }
  }
  input.value = '';
}

function addThumb(att) {
  const container = document.getElementById('existingAttachments') || (() => {
    const d = document.createElement('div');
    d.id = 'existingAttachments';
    d.className = 'd-flex gap-2 flex-wrap mb-2';
    document.getElementById('attachmentInput').closest('label').insertAdjacentElement('beforebegin', d);
    return d;
  })();
  const isImg = att.mime_type.startsWith('image/');
  const wrap = document.createElement('div');
  wrap.className = 'position-relative';
  wrap.id = `attThumb_${att.id}`;
  wrap.style.cssText = 'width:64px;height:64px';
  wrap.innerHTML = isImg
    ? `<img src="/attachments/${att.id}" class="rounded border" style="width:64px;height:64px;object-fit:cover">`
    : `<div class="rounded border bg-body-secondary d-flex flex-column align-items-center justify-content-center" style="width:64px;height:64px"><i class="bi bi-file-earmark-pdf text-danger fs-4"></i><span class="text-muted" style="font-size:9px">PDF</span></div>`;
  wrap.innerHTML += `<button type="button" class="btn btn-danger btn-sm position-absolute top-0 end-0 p-0 lh-1" style="width:18px;height:18px;font-size:10px;border-radius:50%" onclick="deleteAttachment(${att.id}, this)">✕</button>`;
  container.appendChild(wrap);
}

async function deleteAttachment(attId, btn) {
  const errEl = document.getElementById('attachUploadError');
  errEl.classList.add('d-none');
  try {
    const res = await fetch(`/attachments/${attId}`, {
      method: 'DELETE',
      headers: {'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content},
    });
    if (!res.ok) { errEl.textContent = (await res.json()).error || 'Ошибка удаления'; errEl.classList.remove('d-none'); return; }
    document.getElementById(`attThumb_${attId}`).remove();
  } catch { errEl.textContent = 'Ошибка сети'; errEl.classList.remove('d-none'); }
}
{% endif %}
```

- [ ] **Step 4: Start the app and verify visually**

```bash
python3 app.py
```

1. Go to `/expenses/add` — should see "Вложения" section with file input
2. Add expense with a JPEG — should succeed
3. Go to `/expenses/<id>/edit` — should see existing attachment thumbnail with ✕ button
4. Upload another file from edit page — should appear without page reload
5. Click ✕ on a thumbnail — should remove it without page reload

- [ ] **Step 5: Commit**

```bash
git add templates/expenses/form.html
git commit -m "feat: add attachments section to expense form (upload + AJAX delete)"
```

---

## Task 6: Expense list — paperclip badge + preview modal

**Files:**
- Modify: `app.py` — `expenses_list()` to eager-load attachment counts
- Modify: `templates/expenses/list.html`

- [ ] **Step 1: Update `expenses_list()` in `app.py` to eager-load attachments**

In the `expenses_list()` function, change the query chain for expenses to use `options(db.joinedload(Expense.attachments))`:

```python
from sqlalchemy.orm import joinedload  # add this import near top of file with other imports

# In expenses_list(), change:
#   expenses = query.all()
# To:
expenses = query.options(joinedload(Expense.attachments)).all()
```

Add `from sqlalchemy.orm import joinedload` near the top of app.py where SQLAlchemy symbols are imported (check current imports for `extract`, `func` etc. and add alongside).

- [ ] **Step 2: Pass attachment data to template via data attribute**

In `templates/expenses/list.html`, find the expense card loop (the `<div class="record-card ...">` block). After the amount span and before the edit/delete buttons, add the paperclip badge:

Find the block that shows the amount (contains `exp.amount`) and add after it:

```html
{% if exp.attachments %}
<span class="badge bg-primary bg-opacity-10 text-primary"
      style="cursor:pointer;font-size:11px"
      data-attachments='{{ exp.attachments | map(attribute="id") | list | tojson }}'
      data-filenames='{{ exp.attachments | map(attribute="filename") | list | tojson }}'
      data-mimes='{{ exp.attachments | map(attribute="mime_type") | list | tojson }}'
      data-label='{{ exp.description or "" }}'
      onclick="openAttachmentsModal(this)">
  <i class="bi bi-paperclip"></i>{{ exp.attachments | length }}
</span>
{% endif %}
```

- [ ] **Step 3: Add the attachments modal and JS to `list.html`**

In the `{% block scripts %}` section at the bottom of `list.html` (after the existing `setSort` script block), add:

```html
{% block modals %}
<!-- Attachments preview modal -->
<div class="modal fade" id="attachmentsModal" tabindex="-1" aria-labelledby="attachmentsModalLabel">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content">
      <div class="modal-header border-0 pb-0">
        <h6 class="modal-title fw-semibold" id="attachmentsModalLabel">Вложения</h6>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body" id="attachmentsModalBody"></div>
    </div>
  </div>
</div>
{% endblock %}
```

Then inside `{% block scripts %}`, append after the existing script:

```html
<script>
function openAttachmentsModal(el) {
  const ids      = JSON.parse(el.dataset.attachments);
  const names    = JSON.parse(el.dataset.filenames);
  const mimes    = JSON.parse(el.dataset.mimes);
  const label    = el.dataset.label;

  document.getElementById('attachmentsModalLabel').textContent =
    (label ? label + ' · ' : '') + ids.length + ' ' + (ids.length === 1 ? 'файл' : 'файла');

  const body = document.getElementById('attachmentsModalBody');
  body.innerHTML = '';

  ids.forEach((id, i) => {
    const isImg = mimes[i].startsWith('image/');
    const item = document.createElement('div');
    item.className = 'mb-3';
    if (isImg) {
      item.innerHTML = `
        <a href="/attachments/${id}" target="_blank">
          <img src="/attachments/${id}" class="img-fluid rounded w-100" style="max-height:300px;object-fit:contain">
        </a>
        <div class="text-muted small mt-1">${names[i]}</div>`;
    } else {
      item.innerHTML = `
        <div class="d-flex align-items-center gap-3 p-2 border rounded">
          <i class="bi bi-file-earmark-pdf text-danger fs-2"></i>
          <div class="flex-fill">
            <div class="fw-semibold small">${names[i]}</div>
          </div>
          <a href="/attachments/${id}" download="${names[i]}" class="btn btn-sm btn-outline-primary">
            <i class="bi bi-download me-1"></i>Скачать
          </a>
        </div>`;
    }
    body.appendChild(item);
  });

  new bootstrap.Modal(document.getElementById('attachmentsModal')).show();
}
</script>
```

**Note:** Check if `list.html` already has a `{% block modals %}` — if so, add the modal HTML inside that existing block. If it already has a `{% block scripts %}`, append inside it rather than creating a new one.

- [ ] **Step 4: Start the app and verify visually**

```bash
python3 app.py
```

1. Go to `/expenses` — expenses WITH attachments should show blue 📎N badge
2. Click badge — modal opens with image preview (click to open full-size) or PDF download link
3. Expenses WITHOUT attachments show no badge

- [ ] **Step 5: Run full test suite**

```bash
python3 -m pytest tests/ -q
```

Expected: **46 passed** (no regressions — template changes have no test impact)

- [ ] **Step 6: Commit**

```bash
git add app.py templates/expenses/list.html
git commit -m "feat: add paperclip badge and attachment preview modal to expenses list"
```

---

## Verification Checklist

End-to-end smoke test after all tasks:

1. **Add expense with files** — go to `/expenses/add`, fill form, attach 2 JPEGs, submit → expense created with attachments
2. **Edit expense** — go to edit page, see thumbnails, click ✕ on one → removed without reload; upload new PDF → appears without reload
3. **List badge** — go to `/expenses`, see 📎1 badge on the expense → click → modal shows image + PDF
4. **Access control** — log in as second user, try `GET /attachments/<id>` → 403
5. **Delete cascade** — delete an expense → its attachments gone from DB (verify in `/admin` or DB)
6. **File validation** — upload a `.exe` → rejected; upload 11 MB file → rejected
