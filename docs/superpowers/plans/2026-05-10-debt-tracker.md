# Debt Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a debt tracker — a page to record money owed to/by others, with a summary card on the dashboard.

**Architecture:** New `Debt` SQLAlchemy model + 5 CRUD routes in `app.py` + `inject_debt_summary` context processor. Templates follow existing `record-card` / Bootstrap patterns. Navbar gets a new "Долги" link. Dashboard shows a summary card when active debts exist.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, Bootstrap 5. No new dependencies.

---

## File Map

| File | Action |
|------|--------|
| `app.py` | Add `Debt` model; add 5 routes; add `inject_debt_summary` context processor |
| `tests/conftest.py` | Add `Debt` to `clean_db` teardown |
| `tests/test_debts.py` | Create — 6 tests |
| `templates/debts/list.html` | Create — debt list page |
| `templates/debts/edit.html` | Create — edit form page |
| `templates/base.html` | Add "Долги" nav-item after Накопления |
| `templates/index.html` | Add debt summary card after savings block |

---

## Task 1: `Debt` model + conftest update + failing tests

**Files:**
- Modify: `app.py` — add `Debt` class after `ExpenseAttachment`
- Modify: `tests/conftest.py` — add `Debt` to cleanup
- Create: `tests/test_debts.py`

- [ ] **Step 1: Add `Debt` model to `app.py`**

Find `class ExpenseAttachment(db.Model):` block (≈ line 253). Add after it:

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

- [ ] **Step 2: Update `tests/conftest.py` to clean `Debt` rows**

Find the `clean_db` fixture import line:

```python
        from app import (User, Expense, Income, MonthlyBudget,
                         Category, ExpenseAttachment, SavingsAccount)
```

Replace with:

```python
        from app import (User, Expense, Income, MonthlyBudget,
                         Category, ExpenseAttachment, SavingsAccount, Debt)
```

Then add before `db.session.query(SavingsAccount).delete()`:

```python
        db.session.query(Debt).delete()
```

- [ ] **Step 3: Create `tests/test_debts.py`**

```python
import pytest
from app import app as flask_app, db, Debt


def _register_and_login(client, username='debtuser', password='pass1234'):
    client.post('/register', data={
        'username': username, 'email': f'{username}@example.com',
        'password': password, 'confirm': password,
    }, follow_redirects=True)
    client.post('/login', data={'login': username, 'password': password},
                follow_redirects=True)


def test_debts_list_requires_auth(client):
    """GET /debts without login redirects."""
    resp = client.get('/debts', follow_redirects=False)
    assert resp.status_code == 302


def test_debt_add_owe(client):
    """POST /debts/add with direction=owe creates debt and flashes success."""
    _register_and_login(client)
    resp = client.post('/debts/add',
                       data={'person_name': 'Ваня', 'amount': '5000', 'direction': 'owe'},
                       follow_redirects=True)
    assert resp.status_code == 200
    assert 'Долг добавлен'.encode() in resp.data


def test_debt_add_owed(client):
    """POST /debts/add with direction=owed stores correct record."""
    _register_and_login(client)
    client.post('/debts/add',
                data={'person_name': 'Петя', 'amount': '3000', 'direction': 'owed'},
                follow_redirects=True)
    with flask_app.app_context():
        d = Debt.query.filter_by(person_name='Петя').first()
        assert d is not None
        assert d.direction == 'owed'
        assert float(d.amount) == 3000.0


def test_debt_toggle_paid(client):
    """POST /debts/<id>/toggle-paid flips is_paid from False to True."""
    _register_and_login(client)
    client.post('/debts/add',
                data={'person_name': 'Маша', 'amount': '1000', 'direction': 'owe'},
                follow_redirects=True)
    with flask_app.app_context():
        debt_id = Debt.query.filter_by(person_name='Маша').first().id
    client.post(f'/debts/{debt_id}/toggle-paid', follow_redirects=True)
    with flask_app.app_context():
        assert db.session.get(Debt, debt_id).is_paid is True


def test_debt_delete(client):
    """POST /debts/<id>/delete removes the record."""
    _register_and_login(client)
    client.post('/debts/add',
                data={'person_name': 'Саша', 'amount': '500', 'direction': 'owed'},
                follow_redirects=True)
    with flask_app.app_context():
        debt_id = Debt.query.filter_by(person_name='Саша').first().id
    client.post(f'/debts/{debt_id}/delete', follow_redirects=True)
    with flask_app.app_context():
        assert db.session.get(Debt, debt_id) is None


def test_dashboard_shows_debt_card(client):
    """Dashboard shows debt summary card when active debts exist."""
    _register_and_login(client)
    client.post('/debts/add',
                data={'person_name': 'Коля', 'amount': '2000', 'direction': 'owe'},
                follow_redirects=True)
    resp = client.get('/')
    assert resp.status_code == 200
    assert 'Долги'.encode() in resp.data
```

- [ ] **Step 4: Run to verify tests fail**

```bash
cd /Users/k1n4_l0v3d/Desktop/expence_tracker-main
source venv/bin/activate
pytest tests/test_debts.py -v 2>&1 | tail -12
```

Expected: all FAILED — routes don't exist yet (404/redirect).

- [ ] **Step 5: Commit model + conftest + tests**

```bash
git add app.py tests/conftest.py tests/test_debts.py
git commit -m "feat: add Debt model and debt tracker tests"
```

---

## Task 2: CRUD routes

**Files:**
- Modify: `app.py` — add 5 routes before `if __name__ == '__main__':`

- [ ] **Step 1: Add all 5 debt routes to `app.py`**

Find `@app.route('/offline')` and insert ALL routes before it:

```python
# ─── Трекер долгов ────────────────────────────────────────────────────────────

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
    else:  # 'active'
        q = q.filter_by(is_paid=False)
    debts = q.order_by(Debt.created_at.desc()).all()

    all_active = Debt.query.filter_by(user_id=current_user.id, is_paid=False).all()
    total_owe  = sum(float(d.amount) for d in all_active if d.direction == 'owe')
    total_owed = sum(float(d.amount) for d in all_active if d.direction == 'owed')

    return render_template('debts/list.html',
        debts=debts, filter_val=filter_val,
        total_owe=total_owe, total_owed=total_owed)


@app.route('/debts/add', methods=['POST'])
@login_required
@ban_check
def debt_add():
    person    = request.form.get('person_name', '').strip()
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


@app.route('/debts/<int:debt_id>/toggle-paid', methods=['POST'])
@login_required
@ban_check
def debt_toggle_paid(debt_id):
    debt = Debt.query.filter_by(id=debt_id, user_id=current_user.id).first_or_404()
    debt.is_paid = not debt.is_paid
    db.session.commit()
    return redirect(url_for('debts_list'))


@app.route('/debts/<int:debt_id>/delete', methods=['POST'])
@login_required
@ban_check
def debt_delete(debt_id):
    debt = Debt.query.filter_by(id=debt_id, user_id=current_user.id).first_or_404()
    db.session.delete(debt)
    db.session.commit()
    flash('Долг удалён.', 'success')
    return redirect(url_for('debts_list'))


@app.route('/debts/<int:debt_id>/edit', methods=['GET', 'POST'])
@login_required
@ban_check
def debt_edit(debt_id):
    debt = Debt.query.filter_by(id=debt_id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        person    = request.form.get('person_name', '').strip()
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

- [ ] **Step 2: Add `inject_debt_summary` context processor**

Find `@app.context_processor` block for `inject_budget_alerts` (≈ line 1535) and add after it:

```python
@app.context_processor
def inject_debt_summary():
    if not current_user.is_authenticated:
        return {'debt_summary': {'total_owe': 0, 'total_owed': 0,
                                 'count_owe': 0, 'count_owed': 0}}
    active = Debt.query.filter_by(user_id=current_user.id, is_paid=False).all()
    return {'debt_summary': {
        'total_owe':  sum(float(d.amount) for d in active if d.direction == 'owe'),
        'total_owed': sum(float(d.amount) for d in active if d.direction == 'owed'),
        'count_owe':  sum(1 for d in active if d.direction == 'owe'),
        'count_owed': sum(1 for d in active if d.direction == 'owed'),
    }}
```

- [ ] **Step 3: Run backend tests**

```bash
pytest tests/test_debts.py -v 2>&1 | tail -12
```

Expected: all 6 PASSED (templates don't need to exist for most route tests since they redirect).

If `test_dashboard_shows_debt_card` fails because `debts/list.html` doesn't exist yet, that's expected — fix after Task 3.

- [ ] **Step 4: Commit routes**

```bash
git add app.py
git commit -m "feat: add debt CRUD routes and inject_debt_summary context processor"
```

---

## Task 3: Templates

**Files:**
- Create: `templates/debts/list.html`
- Create: `templates/debts/edit.html`

- [ ] **Step 1: Create `templates/debts/` directory**

```bash
mkdir -p /Users/k1n4_l0v3d/Desktop/expence_tracker-main/templates/debts
```

- [ ] **Step 2: Create `templates/debts/list.html`**

Create `/Users/k1n4_l0v3d/Desktop/expence_tracker-main/templates/debts/list.html`:

```html
{% extends 'base.html' %}
{% block title %}Долги{% endblock %}

{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
    <h4 class="mb-0 fw-bold"><i class="bi bi-arrow-left-right text-primary me-2"></i>Долги</h4>
    <button type="button" class="btn grad-primary btn-sm" data-bs-toggle="modal" data-bs-target="#addDebtModal">
        <i class="bi bi-plus-lg me-1"></i>Добавить
    </button>
</div>

{% if total_owe > 0 or total_owed > 0 %}
<div class="row g-3 mb-4">
    {% if total_owe > 0 %}
    <div class="col-sm-6">
        <div class="card border-0 shadow-sm h-100" style="background:#fff1f2">
            <div class="card-body text-center py-3">
                <div class="small text-muted mb-1">Я должен</div>
                <div class="fw-bold fs-4 text-danger">{{ total_owe|fmt_rub }} ₽</div>
            </div>
        </div>
    </div>
    {% endif %}
    {% if total_owed > 0 %}
    <div class="col-sm-6">
        <div class="card border-0 shadow-sm h-100" style="background:#f0fdf4">
            <div class="card-body text-center py-3">
                <div class="small text-muted mb-1">Мне должны</div>
                <div class="fw-bold fs-4 text-success">{{ total_owed|fmt_rub }} ₽</div>
            </div>
        </div>
    </div>
    {% endif %}
</div>
{% endif %}

<!-- Фильтр -->
<div class="d-flex gap-2 mb-3 flex-wrap">
    {% for key, label in [('active','Активные'),('owe','Я должен'),('owed','Мне должны'),('paid','Погашены')] %}
    <a href="?filter={{ key }}"
       class="btn btn-sm {% if filter_val == key %}grad-primary{% else %}btn-outline-secondary{% endif %}">
        {{ label }}
    </a>
    {% endfor %}
</div>

<div>
{% for debt in debts %}
<div class="record-card stagger-item d-flex justify-content-between align-items-center gap-2
    {% if debt.is_paid %}opacity-50{% endif %}">
    <div>
        <div class="d-flex align-items-center gap-2 mb-1">
            {% if debt.direction == 'owe' %}
            <span class="badge" style="background:#dc3545">Я должен</span>
            {% else %}
            <span class="badge" style="background:#198754">Мне должны</span>
            {% endif %}
            {% if debt.is_paid %}
            <span class="badge bg-secondary">Погашен</span>
            {% endif %}
        </div>
        <div class="fw-semibold {% if debt.is_paid %}text-decoration-line-through{% endif %}">
            {{ debt.person_name }}
        </div>
        <div class="text-muted small">{{ debt.created_at.strftime('%d.%m.%Y') }}</div>
    </div>
    <div class="text-end flex-shrink-0">
        <div class="fw-bold fs-6 {% if debt.direction == 'owe' %}text-danger{% else %}text-success{% endif %}
             {% if debt.is_paid %}text-decoration-line-through{% endif %}">
            {{ debt.amount|fmt_rub }} ₽
        </div>
        <div class="d-flex gap-1 mt-1 justify-content-end">
            <form method="post" action="{{ url_for('debt_toggle_paid', debt_id=debt.id) }}" class="d-inline">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <button class="btn btn-sm {% if debt.is_paid %}btn-outline-secondary{% else %}btn-outline-success{% endif %}"
                        style="min-height:34px;padding:4px 8px"
                        title="{% if debt.is_paid %}Вернуть{% else %}Погасить{% endif %}">
                    <i class="bi {% if debt.is_paid %}bi-arrow-counterclockwise{% else %}bi-check-lg{% endif %}"></i>
                </button>
            </form>
            <a href="{{ url_for('debt_edit', debt_id=debt.id) }}"
               class="btn btn-sm btn-outline-secondary" style="min-height:34px;padding:4px 8px">
                <i class="bi bi-pencil"></i>
            </a>
            <form method="post" action="{{ url_for('debt_delete', debt_id=debt.id) }}" class="d-inline">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <button class="btn btn-sm btn-outline-danger" style="min-height:34px;padding:4px 8px"
                        onclick="return confirm('Удалить этот долг?')">
                    <i class="bi bi-trash"></i>
                </button>
            </form>
        </div>
    </div>
</div>
{% else %}
<div class="text-center text-muted py-5">
    <i class="bi bi-arrow-left-right" style="font-size:2.5rem;opacity:.3"></i>
    <div class="mt-2">Долгов нет</div>
    <button type="button" class="btn grad-primary btn-sm mt-3"
            data-bs-toggle="modal" data-bs-target="#addDebtModal">
        <i class="bi bi-plus-lg me-1"></i>Добавить первый долг
    </button>
</div>
{% endfor %}
</div>
{% endblock %}

{% block modals %}
<div class="modal fade" id="addDebtModal" tabindex="-1">
    <div class="modal-dialog modal-dialog-centered modal-sm">
        <div class="modal-content">
            <div class="modal-header border-0">
                <h6 class="modal-title fw-semibold">
                    <i class="bi bi-arrow-left-right text-primary me-1"></i>Новый долг
                </h6>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <form method="post" action="{{ url_for('debt_add') }}">
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                <div class="modal-body pt-0">
                    <div class="mb-3">
                        <label class="form-label fw-semibold">Имя *</label>
                        <input type="text" name="person_name" class="form-control"
                               required maxlength="100" placeholder="Имя человека">
                    </div>
                    <div class="mb-3">
                        <label class="form-label fw-semibold">Сумма *</label>
                        <div class="input-group">
                            <input type="number" name="amount" class="form-control"
                                   min="0.01" step="0.01" required placeholder="0.00">
                            <span class="input-group-text">₽</span>
                        </div>
                    </div>
                    <div class="mb-2">
                        <label class="form-label fw-semibold">Направление</label>
                        <div class="d-flex gap-3">
                            <div class="form-check">
                                <input class="form-check-input" type="radio"
                                       name="direction" value="owe" id="dirOwe" checked>
                                <label class="form-check-label" for="dirOwe">Я должен</label>
                            </div>
                            <div class="form-check">
                                <input class="form-check-input" type="radio"
                                       name="direction" value="owed" id="dirOwed">
                                <label class="form-check-label" for="dirOwed">Мне должны</label>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="modal-footer border-0 pt-0">
                    <button type="button" class="btn btn-outline-secondary btn-sm"
                            data-bs-dismiss="modal">Отмена</button>
                    <button type="submit" class="btn grad-primary btn-sm">Добавить</button>
                </div>
            </form>
        </div>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Create `templates/debts/edit.html`**

Create `/Users/k1n4_l0v3d/Desktop/expence_tracker-main/templates/debts/edit.html`:

```html
{% extends 'base.html' %}
{% block title %}Редактировать долг{% endblock %}

{% block content %}
<div class="row justify-content-center">
    <div class="col-md-5">
        <div class="card shadow-sm border-0">
            <div class="card-header border-0 fw-semibold pt-3">
                <i class="bi bi-pencil text-primary me-2"></i>Редактировать долг
            </div>
            <div class="card-body">
                <form method="post">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <div class="mb-3">
                        <label class="form-label fw-semibold">Имя *</label>
                        <input type="text" name="person_name" class="form-control"
                               required maxlength="100" value="{{ debt.person_name }}">
                    </div>
                    <div class="mb-3">
                        <label class="form-label fw-semibold">Сумма *</label>
                        <div class="input-group">
                            <input type="number" name="amount" class="form-control"
                                   min="0.01" step="0.01" required
                                   value="{{ "%.2f"|format(debt.amount|float) }}">
                            <span class="input-group-text">₽</span>
                        </div>
                    </div>
                    <div class="mb-4">
                        <label class="form-label fw-semibold">Направление</label>
                        <div class="d-flex gap-3">
                            <div class="form-check">
                                <input class="form-check-input" type="radio"
                                       name="direction" value="owe" id="dirOwe"
                                       {% if debt.direction == 'owe' %}checked{% endif %}>
                                <label class="form-check-label" for="dirOwe">Я должен</label>
                            </div>
                            <div class="form-check">
                                <input class="form-check-input" type="radio"
                                       name="direction" value="owed" id="dirOwed"
                                       {% if debt.direction == 'owed' %}checked{% endif %}>
                                <label class="form-check-label" for="dirOwed">Мне должны</label>
                            </div>
                        </div>
                    </div>
                    <div class="d-flex gap-2">
                        <button type="submit" class="btn grad-primary">
                            <i class="bi bi-check-lg me-1"></i>Сохранить
                        </button>
                        <a href="{{ url_for('debts_list') }}" class="btn btn-outline-secondary">
                            Отмена
                        </a>
                    </div>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/test_debts.py -v 2>&1 | tail -12
```

Expected: 6 PASSED

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -q 2>&1 | tail -3
```

Expected: 108 passed (102 + 6)

- [ ] **Step 6: Commit templates**

```bash
git add templates/debts/
git commit -m "feat: add debt tracker templates (list + edit)"
```

---

## Task 4: Navbar + dashboard card

**Files:**
- Modify: `templates/base.html` — add nav-item
- Modify: `templates/index.html` — add debt summary card

- [ ] **Step 1: Add "Долги" to navbar in `templates/base.html`**

Find the Накопления nav-item (≈ line 86):

```html
                <li class="nav-item">
                    <a class="nav-link {% if request.endpoint and 'savings' in request.endpoint %}active{% endif %}"
                       href="{{ url_for('savings_list') }}">
                        <i class="bi bi-safe me-1"></i>Накопления
                    </a>
                </li>
```

Add immediately after it:

```html
                <li class="nav-item">
                    <a class="nav-link {% if request.endpoint and 'debt' in request.endpoint %}active{% endif %}"
                       href="{{ url_for('debts_list') }}">
                        <i class="bi bi-arrow-left-right me-1"></i>Долги
                    </a>
                </li>
```

- [ ] **Step 2: Add debt summary card to `templates/index.html`**

Find this exact block in `templates/index.html` (the end of the savings section):

```html
            {% endfor %}
        </div>
    </div>
</div>
{% endif %}
```

This is the `{% endif %}` closing `{% if savings_data %}`. Add immediately after it:

```html
{% if debt_summary.total_owe > 0 or debt_summary.total_owed > 0 %}
<div class="card shadow-sm border-0 mb-4">
    <div class="card-header bg-body fw-semibold border-0 pt-3 d-flex justify-content-between align-items-center">
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

- [ ] **Step 3: Verify template syntax**

```bash
source venv/bin/activate
python -c "
from app import app
with app.app_context():
    for tpl in ['base.html', 'index.html', 'debts/list.html', 'debts/edit.html']:
        app.jinja_env.parse(open(f'templates/{tpl}').read())
        print(f'OK: {tpl}')
"
```

Expected: 4 lines of `OK: ...`

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/ -q 2>&1 | tail -3
```

Expected: 108 passed, 0 failed

- [ ] **Step 5: Commit**

```bash
git add templates/base.html templates/index.html
git commit -m "feat: add Долги nav link and dashboard debt summary card"
```

---

## Task 5: Final verification

- [ ] **Step 1: Verify app imports cleanly**

```bash
source venv/bin/activate
python -c "from app import app, Debt, debts_list, debt_add, debt_toggle_paid, debt_delete, debt_edit; print('All OK')"
```

Expected: `All OK`

- [ ] **Step 2: Run full suite**

```bash
pytest tests/ -v 2>&1 | grep -E "PASSED|FAILED|ERROR" | wc -l
pytest tests/ -q 2>&1 | tail -3
```

Expected: 108 passed, 0 failed
