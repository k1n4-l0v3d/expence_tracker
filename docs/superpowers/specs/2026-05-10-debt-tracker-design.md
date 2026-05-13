# Debt Tracker — Design Spec

**Date:** 2026-05-10
**Status:** Approved

---

## Problem

No way to track informal debts — money owed to others or owed by others. Users resort to notes or memory.

## Solution

New `Debt` model with minimal fields. Dedicated `/debts` page with one table, direction filter, and toggle-paid action. Summary card on the dashboard shown only when active debts exist. Navbar link added.

---

## Model

### `Debt` (table: `debts`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer PK | |
| `user_id` | Integer FK → users | |
| `person_name` | String(100), not null | Who owes / is owed |
| `amount` | Numeric(12,2), not null | |
| `direction` | String(4), not null | `'owe'` = I owe them; `'owed'` = they owe me |
| `is_paid` | Boolean, default False | |
| `created_at` | DateTime, default utcnow | |

---

## Routes

| Method | URL | Auth | Action |
|--------|-----|------|--------|
| GET | `/debts` | ✅ | List all debts; `?filter=owe\|owed\|paid\|all` (default `all`) |
| POST | `/debts/add` | ✅ | Create debt, redirect to `/debts` |
| POST | `/debts/<id>/toggle-paid` | ✅ | Toggle `is_paid`, redirect to `/debts` |
| POST | `/debts/<id>/delete` | ✅ | Delete, redirect to `/debts` |
| GET/POST | `/debts/<id>/edit` | ✅ | Edit person_name, amount, direction |

All routes require `@login_required` and `@ban_check`. Edit/delete verify `debt.user_id == current_user.id`.

---

## Backend (`app.py`)

### Model definition

Add after `ExpenseAttachment` class:

```python
class Debt(db.Model):
    __tablename__ = 'debts'

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    person_name = db.Column(db.String(100), nullable=False)
    amount      = db.Column(db.Numeric(12, 2), nullable=False)
    direction   = db.Column(db.String(4), nullable=False)   # 'owe' | 'owed'
    is_paid     = db.Column(db.Boolean, nullable=False, default=False)
    created_at  = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('debts', lazy='dynamic'))
```

### Route: `GET /debts`

```python
@app.route('/debts')
@login_required
@ban_check
def debts_list():
    filter_val = request.args.get('filter', 'active')
    q = Debt.query.filter_by(user_id=current_user.id)
    if filter_val == 'owe':
        q = q.filter_by(direction='owe', is_paid=False)
    elif filter_val == 'owed':
        q = q.filter_by(direction='owed', is_paid=False)
    elif filter_val == 'paid':
        q = q.filter_by(is_paid=True)
    else:  # 'active' — all non-paid
        q = q.filter_by(is_paid=False)
    debts = q.order_by(Debt.created_at.desc()).all()

    all_active = Debt.query.filter_by(user_id=current_user.id, is_paid=False).all()
    total_owe  = sum(float(d.amount) for d in all_active if d.direction == 'owe')
    total_owed = sum(float(d.amount) for d in all_active if d.direction == 'owed')

    return render_template('debts/list.html',
        debts=debts, filter_val=filter_val,
        total_owe=total_owe, total_owed=total_owed)
```

### Route: `POST /debts/add`

```python
@app.route('/debts/add', methods=['POST'])
@login_required
@ban_check
def debt_add():
    person = request.form.get('person_name', '').strip()
    direction = request.form.get('direction', 'owe')
    if not person or direction not in ('owe', 'owed'):
        flash('Заполните все поля.', 'danger')
        return redirect(url_for('debts_list'))
    try:
        amount = float(request.form['amount'])
        if amount <= 0:
            raise ValueError
    except (ValueError, KeyError):
        flash('Некорректная сумма.', 'danger')
        return redirect(url_for('debts_list'))

    db.session.add(Debt(
        user_id=current_user.id, person_name=person,
        amount=amount, direction=direction,
    ))
    db.session.commit()
    flash('Долг добавлен.', 'success')
    return redirect(url_for('debts_list'))
```

### Route: `POST /debts/<id>/toggle-paid`

```python
@app.route('/debts/<int:debt_id>/toggle-paid', methods=['POST'])
@login_required
@ban_check
def debt_toggle_paid(debt_id):
    debt = Debt.query.filter_by(id=debt_id, user_id=current_user.id).first_or_404()
    debt.is_paid = not debt.is_paid
    db.session.commit()
    return redirect(url_for('debts_list'))
```

### Route: `POST /debts/<id>/delete`

```python
@app.route('/debts/<int:debt_id>/delete', methods=['POST'])
@login_required
@ban_check
def debt_delete(debt_id):
    debt = Debt.query.filter_by(id=debt_id, user_id=current_user.id).first_or_404()
    db.session.delete(debt)
    db.session.commit()
    flash('Долг удалён.', 'success')
    return redirect(url_for('debts_list'))
```

### Route: `GET/POST /debts/<id>/edit`

```python
@app.route('/debts/<int:debt_id>/edit', methods=['GET', 'POST'])
@login_required
@ban_check
def debt_edit(debt_id):
    debt = Debt.query.filter_by(id=debt_id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        person = request.form.get('person_name', '').strip()
        direction = request.form.get('direction', debt.direction)
        if not person or direction not in ('owe', 'owed'):
            flash('Заполните все поля.', 'danger')
            return redirect(url_for('debt_edit', debt_id=debt_id))
        try:
            amount = float(request.form['amount'])
            if amount <= 0:
                raise ValueError
        except (ValueError, KeyError):
            flash('Некорректная сумма.', 'danger')
            return redirect(url_for('debt_edit', debt_id=debt_id))
        debt.person_name = person
        debt.amount      = amount
        debt.direction   = direction
        db.session.commit()
        flash('Долг обновлён.', 'success')
        return redirect(url_for('debts_list'))
    return render_template('debts/edit.html', debt=debt)
```

### SQLite migration

```python
# Inside the `with app.app_context(): db.create_all()` block at startup:
# db.create_all() handles new table automatically.
```

---

## Templates

### `templates/debts/list.html`

Extends `base.html`. Structure:

1. **Header row** — "Долги" title + "+ Добавить" button (opens `#addDebtModal`)
2. **Summary cards** — two side-by-side cards:
   - "Я должен: `total_owe|fmt_rub` ₽" (red tint)
   - "Мне должны: `total_owed|fmt_rub` ₽" (green tint)
   - Hidden if both are 0
3. **Filter pills** — `[Активные] [Я должен] [Мне должны] [Погашены]` — links with `?filter=...`; active pill highlighted
4. **Debt list** — `record-card` style per debt:
   - Direction badge: `🔴 Я должен` or `🟢 Мне должны`
   - Person name (bold) + amount (`fmt_rub`)
   - Paid debts: row dimmed, amount strikethrough, badge "Погашен"
   - Action buttons: ✓ (toggle-paid form), ✏️ (edit link), 🗑 (delete form)
5. **Empty state** — "Долгов нет" with icon

### `templates/debts/edit.html`

Simple page (same pattern as `expenses/form.html`) with the three fields and Save/Cancel buttons.

### `templates/debts/_add_modal.html` (included in list.html via `{% include %}`)

Bootstrap modal `#addDebtModal`:

```html
<div class="mb-3">
  <label class="form-label fw-semibold">Имя *</label>
  <input type="text" name="person_name" class="form-control" required maxlength="100">
</div>
<div class="mb-3">
  <label class="form-label fw-semibold">Сумма *</label>
  <input type="number" name="amount" class="form-control" min="0.01" step="0.01" required>
</div>
<div class="mb-3">
  <label class="form-label fw-semibold">Направление</label>
  <div class="d-flex gap-3">
    <div class="form-check">
      <input class="form-check-input" type="radio" name="direction" value="owe" id="dirOwe" checked>
      <label class="form-check-label" for="dirOwe">Я должен</label>
    </div>
    <div class="form-check">
      <input class="form-check-input" type="radio" name="direction" value="owed" id="dirOwed">
      <label class="form-check-label" for="dirOwed">Мне должны</label>
    </div>
  </div>
</div>
```

---

## Dashboard card (`templates/index.html`)

Add after the savings section (`{% if savings_data %}...{% endif %}`), before the row with categories:

```html
{% if debt_summary.total_owe > 0 or debt_summary.total_owed > 0 %}
<div class="card shadow-sm border-0 mb-4">
    <div class="card-header bg-body fw-semibold border-0 pt-3 d-flex justify-content-between">
        <span><i class="bi bi-arrow-left-right text-primary me-2"></i>Долги</span>
        <a href="{{ url_for('debts_list') }}" class="small">все →</a>
    </div>
    <div class="card-body d-flex gap-3 flex-wrap">
        {% if debt_summary.total_owe > 0 %}
        <div class="border rounded-3 p-3 flex-fill text-center" style="border-color:#dc354555!important">
            <div class="small text-muted mb-1">Я должен</div>
            <div class="fw-bold text-danger fs-5">{{ debt_summary.total_owe|fmt_rub }} ₽</div>
            <div class="small text-muted">{{ debt_summary.count_owe }} чел.</div>
        </div>
        {% endif %}
        {% if debt_summary.total_owed > 0 %}
        <div class="border rounded-3 p-3 flex-fill text-center" style="border-color:#19875455!important">
            <div class="small text-muted mb-1">Мне должны</div>
            <div class="fw-bold text-success fs-5">{{ debt_summary.total_owed|fmt_rub }} ₽</div>
            <div class="small text-muted">{{ debt_summary.count_owed }} чел.</div>
        </div>
        {% endif %}
    </div>
</div>
{% endif %}
```

### Context processor `inject_debt_summary`

Add alongside `inject_reminders`:

```python
@app.context_processor
def inject_debt_summary():
    if not current_user.is_authenticated:
        return {'debt_summary': {'total_owe': 0, 'total_owed': 0, 'count_owe': 0, 'count_owed': 0}}
    active = Debt.query.filter_by(user_id=current_user.id, is_paid=False).all()
    return {'debt_summary': {
        'total_owe':  sum(float(d.amount) for d in active if d.direction == 'owe'),
        'total_owed': sum(float(d.amount) for d in active if d.direction == 'owed'),
        'count_owe':  sum(1 for d in active if d.direction == 'owe'),
        'count_owed': sum(1 for d in active if d.direction == 'owed'),
    }}
```

---

## Navbar (`templates/base.html`)

Add after the Savings nav-item:

```html
<li class="nav-item">
    <a class="nav-link {% if request.endpoint and 'debt' in request.endpoint %}active{% endif %}"
       href="{{ url_for('debts_list') }}">
        <i class="bi bi-arrow-left-right me-1"></i>Долги
    </a>
</li>
```

---

## `conftest.py` — clean_db update

Add `Debt` to the teardown cleanup:

```python
from app import (..., Debt)
db.session.query(Debt).delete()
```

---

## Tests (`tests/test_debts.py`)

```python
def test_debts_list_requires_auth(client):
    resp = client.get('/debts', follow_redirects=False)
    assert resp.status_code == 302

def test_debt_add_owe(client):
    _register_and_login(client)
    resp = client.post('/debts/add',
        data={'person_name': 'Ваня', 'amount': '5000', 'direction': 'owe'},
        follow_redirects=True)
    assert resp.status_code == 200
    assert 'Долг добавлен'.encode() in resp.data

def test_debt_add_owed(client):
    _register_and_login(client)
    resp = client.post('/debts/add',
        data={'person_name': 'Петя', 'amount': '3000', 'direction': 'owed'},
        follow_redirects=True)
    assert resp.status_code == 200
    with flask_app.app_context():
        from app import Debt
        d = Debt.query.filter_by(person_name='Петя').first()
        assert d is not None
        assert d.direction == 'owed'
        assert float(d.amount) == 3000.0

def test_debt_toggle_paid(client):
    _register_and_login(client)
    client.post('/debts/add',
        data={'person_name': 'Маша', 'amount': '1000', 'direction': 'owe'},
        follow_redirects=True)
    with flask_app.app_context():
        from app import Debt
        d = Debt.query.filter_by(person_name='Маша').first()
        debt_id = d.id
        assert d.is_paid is False
    client.post(f'/debts/{debt_id}/toggle-paid', follow_redirects=True)
    with flask_app.app_context():
        from app import Debt
        assert Debt.query.get(debt_id).is_paid is True

def test_debt_delete(client):
    _register_and_login(client)
    client.post('/debts/add',
        data={'person_name': 'Саша', 'amount': '500', 'direction': 'owed'},
        follow_redirects=True)
    with flask_app.app_context():
        from app import Debt
        debt_id = Debt.query.filter_by(person_name='Саша').first().id
    client.post(f'/debts/{debt_id}/delete', follow_redirects=True)
    with flask_app.app_context():
        from app import Debt
        assert Debt.query.get(debt_id) is None

def test_dashboard_shows_debt_card(client):
    _register_and_login(client)
    client.post('/debts/add',
        data={'person_name': 'Коля', 'amount': '2000', 'direction': 'owe'},
        follow_redirects=True)
    resp = client.get('/')
    assert resp.status_code == 200
    assert 'Долги'.encode() in resp.data
```

---

## Out of Scope

- Due dates / reminders for specific deadlines
- Partial repayments / payment history
- Notifications / push alerts
- Currency other than RUB
- Multi-person splits
