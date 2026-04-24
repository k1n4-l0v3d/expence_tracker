# Накопительные счета — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить накопительные счета (копилки) с балансом, пополнением/снятием и прогресс-баром к цели; пополнение уменьшает месячный баланс, снятие — увеличивает.

**Architecture:** Новая модель `SavingsAccount`. Пополнение создаёт `Expense` со ссылкой на счёт (уменьшает месячный баланс автоматически), снятие создаёт `Income` со ссылкой на счёт (увеличивает). Баланс счёта = SUM(deposits as Expense) − SUM(withdrawals as Income).

**Tech Stack:** Flask, SQLAlchemy, SQLite (тесты) / PostgreSQL (прод), Bootstrap 5, Jinja2, pytest

---

## File Map

| Файл | Действие | Что меняется |
|---|---|---|
| `app.py` | Modify | Модель SavingsAccount, FK в Expense/Income, хелперы, 7 новых маршрутов, обновлён index() |
| `tests/conftest.py` | Modify | SavingsAccount в clean_db |
| `tests/test_savings.py` | Create | Все тесты по накоплениям |
| `templates/savings/list.html` | Create | Страница /savings |
| `templates/savings/form.html` | Create | Форма редактирования счёта |
| `templates/base.html` | Modify | Ссылка «Накопления» в навигации |
| `templates/index.html` | Modify | Блок накоплений + модальные окна |
| `templates/expenses/list.html` | Modify | Бейдж 🏦 у пополнений |
| `templates/income/list.html` | Modify | Бейдж 🏦 у снятий |

---

## Task 1: SavingsAccount model + DB migration

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Write failing test for model creation**

Create `tests/test_savings.py`:

```python
import datetime
import pytest
from app import app as flask_app, db, User, SavingsAccount


@pytest.fixture
def user_client(client):
    with flask_app.app_context():
        u = User(username='saver', email='saver@ex.com', role='user')
        u.set_password('pass')
        db.session.add(u)
        db.session.commit()
        uid = u.id
    client.post('/login', data={'username': 'saver', 'password': 'pass', 'website': ''})
    return client, uid


def test_savings_account_model_creation(user_client):
    """SavingsAccount can be created and persisted."""
    _, uid = user_client
    with flask_app.app_context():
        acc = SavingsAccount(
            user_id=uid,
            name='Отпуск',
            color='#3b82f6',
            target_amount=150000,
        )
        db.session.add(acc)
        db.session.commit()
        assert acc.id is not None
        assert acc.is_active is True
        assert float(acc.target_amount) == 150000.0
        assert acc.icon == 'bi-piggy-bank'
```

- [ ] **Step 2: Run test — must FAIL**

```bash
cd "/Users/k1n4_l0v3d/expence_tracker-main 2" && python -m pytest tests/test_savings.py::test_savings_account_model_creation -v 2>&1 | tail -20
```

Expected: `ImportError: cannot import name 'SavingsAccount'`

- [ ] **Step 3: Add SavingsAccount model to app.py**

Insert after the `Category` class (after line ~162, before `class MonthlyBudget`):

```python
class SavingsAccount(db.Model):
    __tablename__ = 'savings_accounts'

    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name          = db.Column(db.String(100), nullable=False)
    color         = db.Column(db.String(7),  nullable=False, default='#0d6efd')
    icon          = db.Column(db.String(50), nullable=False, default='bi-piggy-bank')
    target_amount = db.Column(db.Numeric(12, 2), nullable=True)
    is_active     = db.Column(db.Boolean, nullable=False, default=True)
    created_at    = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('savings_accounts', lazy='dynamic'))
```

- [ ] **Step 4: Add savings_account_id FK to Income and Expense models**

In `class Income` — append after the `created_at` line:

```python
    savings_account_id = db.Column(db.Integer, db.ForeignKey('savings_accounts.id'), nullable=True)
    savings_account    = db.relationship('SavingsAccount', foreign_keys=[savings_account_id])
```

In `class Expense` — append after the `updated_at` lines, before `attachments`:

```python
    savings_account_id = db.Column(db.Integer, db.ForeignKey('savings_accounts.id'), nullable=True)
    savings_account    = db.relationship('SavingsAccount', foreign_keys=[savings_account_id])
```

- [ ] **Step 5: Add migration to the `with app.app_context():` block**

Append inside the block (after the last `if 'is_spent' not in exp_columns:` block):

```python
    # ── savings_accounts migration ────────────────────────────────
    if 'savings_account_id' not in exp_columns:
        with db.engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE expenses ADD COLUMN savings_account_id INTEGER NULL "
                "REFERENCES savings_accounts(id);"
            ))
            conn.commit()
    inc_columns = [c['name'] for c in inspector.get_columns('incomes')]
    if 'savings_account_id' not in inc_columns:
        with db.engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE incomes ADD COLUMN savings_account_id INTEGER NULL "
                "REFERENCES savings_accounts(id);"
            ))
            conn.commit()
    # Seed system «Накопления» category
    if not Category.query.filter_by(name='Накопления', user_id=None).first():
        db.session.add(Category(
            name='Накопления', icon='bi-piggy-bank', color='#0d6efd', user_id=None,
        ))
        db.session.commit()
```

- [ ] **Step 6: Run test — must PASS**

```bash
python -m pytest tests/test_savings.py::test_savings_account_model_creation -v 2>&1 | tail -10
```

Expected: `PASSED`

- [ ] **Step 7: Commit**

```bash
git add app.py tests/test_savings.py
git commit -m "feat: add SavingsAccount model and DB migration"
```

---

## Task 2: Update conftest.py

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add SavingsAccount to clean_db fixture**

Replace the `clean_db` fixture in `tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
def clean_db():
    """Delete all rows between tests."""
    yield
    with flask_app.app_context():
        from app import (User, Expense, Income, MonthlyBudget,
                         Category, ExpenseAttachment, SavingsAccount)
        db.session.query(ExpenseAttachment).delete()
        db.session.query(MonthlyBudget).delete()
        db.session.query(Expense).delete()
        db.session.query(Income).delete()
        db.session.query(Category).delete()
        db.session.query(SavingsAccount).delete()
        db.session.query(User).delete()
        db.session.commit()
```

- [ ] **Step 2: Run all existing tests — must still PASS**

```bash
python -m pytest tests/ -v 2>&1 | tail -30
```

Expected: все существующие тесты `PASSED`, новый `test_savings_account_model_creation` тоже.

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add SavingsAccount cleanup to conftest"
```

---

## Task 3: get_account_balance helper + balance tests

**Files:**
- Modify: `app.py`
- Modify: `tests/test_savings.py`

- [ ] **Step 1: Add balance tests**

Append to `tests/test_savings.py`:

```python
from app import get_account_balance, Category, Expense, Income
import datetime


@pytest.fixture
def account(user_client):
    """Returns (client, uid, acc_id) with a fresh SavingsAccount."""
    client, uid = user_client
    with flask_app.app_context():
        acc = SavingsAccount(user_id=uid, name='Test', color='#000000')
        db.session.add(acc)
        db.session.commit()
        acc_id = acc.id
    return client, uid, acc_id


def test_balance_empty(account):
    _, uid, acc_id = account
    with flask_app.app_context():
        assert get_account_balance(acc_id) == 0.0


def test_balance_after_deposit(account):
    _, uid, acc_id = account
    with flask_app.app_context():
        cat = Category(name='Накопления', icon='bi-piggy-bank', color='#0d6efd')
        db.session.add(cat)
        db.session.commit()
        exp = Expense(
            user_id=uid, category_id=cat.id, savings_account_id=acc_id,
            amount=10000, expense_date=datetime.date.today(),
            is_spent=True, is_planned=False,
        )
        db.session.add(exp)
        db.session.commit()
        assert get_account_balance(acc_id) == 10000.0


def test_balance_after_deposit_and_withdraw(account):
    _, uid, acc_id = account
    with flask_app.app_context():
        cat = Category(name='Накопления', icon='bi-piggy-bank', color='#0d6efd')
        db.session.add(cat)
        db.session.commit()
        with flask_app.app_context():
            acc = db.session.get(SavingsAccount, acc_id)
        exp = Expense(
            user_id=uid, category_id=cat.id, savings_account_id=acc_id,
            amount=10000, expense_date=datetime.date.today(),
            is_spent=True, is_planned=False,
        )
        inc = Income(
            user_id=uid, savings_account_id=acc_id,
            source='Test', amount=3000,
            income_date=datetime.date.today(),
        )
        db.session.add_all([exp, inc])
        db.session.commit()
        assert get_account_balance(acc_id) == 7000.0
```

- [ ] **Step 2: Run tests — must FAIL**

```bash
python -m pytest tests/test_savings.py -v 2>&1 | tail -20
```

Expected: `ImportError: cannot import name 'get_account_balance'`

- [ ] **Step 3: Add get_account_balance and get_savings_category to app.py**

Insert in the helpers section (after `get_budget_map`, around line ~296):

```python
def get_account_balance(account_id: int) -> float:
    """Deposits are Expense records, withdrawals are Income records."""
    deposited = db.session.query(
        func.coalesce(func.sum(Expense.amount), 0)
    ).filter(Expense.savings_account_id == account_id).scalar()
    withdrawn = db.session.query(
        func.coalesce(func.sum(Income.amount), 0)
    ).filter(Income.savings_account_id == account_id).scalar()
    return float(deposited) - float(withdrawn)


def get_savings_category() -> 'Category':
    """Return (creating if absent) the global system category «Накопления»."""
    cat = Category.query.filter_by(name='Накопления', user_id=None).first()
    if not cat:
        cat = Category(name='Накопления', icon='bi-piggy-bank', color='#0d6efd', user_id=None)
        db.session.add(cat)
        db.session.flush()
    return cat
```

- [ ] **Step 4: Run tests — must PASS**

```bash
python -m pytest tests/test_savings.py -v 2>&1 | tail -20
```

Expected: все 4 теста `PASSED`

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_savings.py
git commit -m "feat: add get_account_balance and get_savings_category helpers"
```

---

## Task 4: CRUD routes + savings page template + nav link

**Files:**
- Modify: `app.py`
- Create: `templates/savings/list.html`
- Create: `templates/savings/form.html`
- Modify: `templates/base.html`

- [ ] **Step 1: Add CRUD tests**

Append to `tests/test_savings.py`:

```python
def test_savings_list_empty(user_client):
    client, _ = user_client
    resp = client.get('/savings')
    assert resp.status_code == 200
    assert 'Накопительные счета' in resp.data.decode()


def test_savings_add_json(user_client):
    client, _ = user_client
    resp = client.post('/savings/add',
                       json={'name': 'Отпуск', 'color': '#3b82f6', 'target_amount': 50000},
                       content_type='application/json')
    assert resp.status_code == 201
    data = resp.get_json()
    assert data['name'] == 'Отпуск'


def test_savings_add_missing_name(user_client):
    client, _ = user_client
    resp = client.post('/savings/add',
                       json={'color': '#000000'},
                       content_type='application/json')
    assert resp.status_code == 400


def test_savings_delete_empty_account(user_client):
    client, uid = user_client
    with flask_app.app_context():
        acc = SavingsAccount(user_id=uid, name='ToDelete', color='#000000')
        db.session.add(acc)
        db.session.commit()
        acc_id = acc.id
    resp = client.delete(f'/savings/{acc_id}')
    assert resp.status_code == 200
    assert resp.get_json()['ok'] is True


def test_savings_delete_with_transactions_rejected(account):
    client, uid, acc_id = account
    with flask_app.app_context():
        cat = Category(name='Накопления', icon='bi-piggy-bank', color='#0d6efd')
        db.session.add(cat)
        db.session.commit()
        exp = Expense(
            user_id=uid, category_id=cat.id, savings_account_id=acc_id,
            amount=1000, expense_date=datetime.date.today(),
            is_spent=True, is_planned=False,
        )
        db.session.add(exp)
        db.session.commit()
    resp = client.delete(f'/savings/{acc_id}')
    assert resp.status_code == 409
```

- [ ] **Step 2: Run CRUD tests — must FAIL**

```bash
python -m pytest tests/test_savings.py::test_savings_list_empty tests/test_savings.py::test_savings_add_json -v 2>&1 | tail -15
```

Expected: `404 NOT FOUND` (route not defined)

- [ ] **Step 3: Add CRUD routes to app.py**

Add in the routes section (after income routes, before API routes, around line ~1607):

```python
# ─── Накопительные счета ──────────────────────────────────────────────────────

@app.route('/savings')
@login_required
@ban_check
def savings_list():
    uid = current_user.id
    accounts = SavingsAccount.query.filter_by(
        user_id=uid, is_active=True
    ).order_by(SavingsAccount.created_at.asc()).all()

    account_data = []
    for acc in accounts:
        balance = get_account_balance(acc.id)
        tx_count = (Expense.query.filter_by(savings_account_id=acc.id).count() +
                    Income.query.filter_by(savings_account_id=acc.id).count())
        pct = None
        if acc.target_amount and float(acc.target_amount) > 0:
            pct = min(round(balance / float(acc.target_amount) * 100, 1), 100.0)
        account_data.append({'acc': acc, 'balance': balance, 'tx_count': tx_count, 'pct': pct})

    deposits = (Expense.query
                .filter(Expense.user_id == uid, Expense.savings_account_id.isnot(None))
                .options(joinedload(Expense.savings_account)).all())
    withdrawals = (Income.query
                   .filter(Income.user_id == uid, Income.savings_account_id.isnot(None))
                   .options(joinedload(Income.savings_account)).all())

    history = []
    for d in deposits:
        history.append({
            'type': 'deposit', 'amount': float(d.amount),
            'description': d.description, 'date': d.expense_date,
            'account_name':  d.savings_account.name  if d.savings_account else '—',
            'account_color': d.savings_account.color if d.savings_account else '#6c757d',
        })
    for w in withdrawals:
        history.append({
            'type': 'withdrawal', 'amount': float(w.amount),
            'description': w.description, 'date': w.income_date,
            'account_name':  w.savings_account.name  if w.savings_account else '—',
            'account_color': w.savings_account.color if w.savings_account else '#6c757d',
        })
    history.sort(key=lambda x: x['date'], reverse=True)

    return render_template('savings/list.html',
                           account_data=account_data,
                           history=history[:50],
                           today=date.today())


@app.route('/savings/add', methods=['POST'])
@login_required
@ban_check
def savings_add():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Название обязательно'}), 400
    if len(name) > 100:
        return jsonify({'error': 'Название слишком длинное'}), 400
    color = (data.get('color') or '#0d6efd').strip()
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        return jsonify({'error': 'Неверный формат цвета'}), 400
    icon = (data.get('icon') or 'bi-piggy-bank').strip()
    target = None
    raw_target = data.get('target_amount')
    if raw_target not in (None, ''):
        try:
            target = float(raw_target)
            if target <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return jsonify({'error': 'Неверная целевая сумма'}), 400
    acc = SavingsAccount(user_id=current_user.id, name=name, color=color,
                         icon=icon, target_amount=target)
    try:
        db.session.add(acc)
        db.session.commit()
        return jsonify({'id': acc.id, 'name': acc.name}), 201
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Ошибка сервера'}), 500


@app.route('/savings/<int:acc_id>/edit', methods=['GET', 'POST'])
@login_required
@ban_check
def savings_edit(acc_id):
    acc = SavingsAccount.query.filter_by(id=acc_id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        color = request.form.get('color', '').strip()
        icon = request.form.get('icon', 'bi-piggy-bank').strip()
        raw_target = request.form.get('target_amount', '').strip()
        if not name:
            flash('Название обязательно.', 'danger')
        elif len(name) > 100:
            flash('Название слишком длинное.', 'danger')
        elif not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            flash('Неверный формат цвета.', 'danger')
        else:
            target = None
            if raw_target:
                try:
                    target = float(raw_target)
                    if target <= 0:
                        raise ValueError
                except (ValueError, TypeError):
                    flash('Неверная целевая сумма.', 'danger')
                    return render_template('savings/form.html', acc=acc)
            acc.name = name
            acc.color = color
            acc.icon = icon
            acc.target_amount = target
            db.session.commit()
            flash('Счёт обновлён!', 'success')
            return redirect(url_for('savings_list'))
    return render_template('savings/form.html', acc=acc)


@app.route('/savings/<int:acc_id>', methods=['DELETE'])
@login_required
def savings_delete(acc_id):
    acc = SavingsAccount.query.filter_by(id=acc_id, user_id=current_user.id).first_or_404()
    tx_count = (Expense.query.filter_by(savings_account_id=acc_id).count() +
                Income.query.filter_by(savings_account_id=acc_id).count())
    if tx_count:
        return jsonify({'error': f'Счёт используется в {tx_count} операциях'}), 409
    try:
        db.session.delete(acc)
        db.session.commit()
        return jsonify({'ok': True})
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Ошибка сервера'}), 500
```

- [ ] **Step 4: Create `templates/savings/` directory and `list.html`**

```bash
mkdir -p "/Users/k1n4_l0v3d/expence_tracker-main 2/templates/savings"
```

Write `templates/savings/list.html`:

```html
{% extends 'base.html' %}
{% block title %}Накопления{% endblock %}

{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4 flex-wrap gap-2">
    <h4 class="mb-0 fw-bold">
        <i class="bi bi-piggy-bank-fill text-primary me-2"></i>Накопительные счета
    </h4>
    <button type="button" class="btn grad-primary btn-sm pulse-btn"
            data-bs-toggle="modal" data-bs-target="#addAccountModal">
        <i class="bi bi-plus-lg me-1"></i>Новый счёт
    </button>
</div>

{% if account_data %}
{% for item in account_data %}
<div class="card shadow-sm border-0 mb-3">
    <div class="card-body">
        <div class="d-flex align-items-center gap-3 mb-2">
            <div class="rounded-3 d-flex align-items-center justify-content-center flex-shrink-0"
                 style="width:44px;height:44px;background:{{ item.acc.color }}22">
                <i class="bi {{ item.acc.icon }} fs-4" style="color:{{ item.acc.color }}"></i>
            </div>
            <div class="flex-grow-1 min-width-0">
                <div class="fw-bold fs-5">{{ item.acc.name }}</div>
                <div class="text-muted small">
                    {{ item.tx_count }} операций · создан {{ item.acc.created_at.strftime('%d.%m.%Y') }}
                </div>
            </div>
            <div class="text-end flex-shrink-0">
                <div class="fw-bold fs-4 text-success">{{ "%.2f"|format(item.balance) }} ₽</div>
                {% if item.acc.target_amount %}
                <div class="text-muted small">цель: {{ "%.0f"|format(item.acc.target_amount|float) }} ₽</div>
                {% endif %}
            </div>
        </div>

        {% if item.acc.target_amount and item.pct is not none %}
        <div class="mb-2">
            <div class="d-flex justify-content-between small text-muted mb-1">
                <span>0 ₽</span>
                <span>{{ item.pct }}% достигнуто</span>
                <span>{{ "%.0f"|format(item.acc.target_amount|float) }} ₽</span>
            </div>
            <div class="progress" style="height:8px;border-radius:6px">
                <div class="progress-bar" role="progressbar"
                     style="width:{{ item.pct }}%;background:{{ item.acc.color }}"
                     aria-valuenow="{{ item.pct }}" aria-valuemin="0" aria-valuemax="100"></div>
            </div>
        </div>
        {% endif %}

        <div class="d-flex gap-2 mt-3 flex-wrap">
            <button type="button" class="btn btn-outline-success btn-sm"
                    onclick="openDepositModal({{ item.acc.id }}, '{{ item.acc.name | e }}', {{ item.balance }})">
                <i class="bi bi-plus-circle me-1"></i>Пополнить
            </button>
            <button type="button" class="btn btn-outline-danger btn-sm"
                    onclick="openWithdrawModal({{ item.acc.id }}, '{{ item.acc.name | e }}', {{ item.balance }})">
                <i class="bi bi-dash-circle me-1"></i>Снять
            </button>
            <div class="ms-auto d-flex gap-1">
                <a href="{{ url_for('savings_edit', acc_id=item.acc.id) }}"
                   class="btn btn-outline-secondary btn-sm" title="Редактировать">
                    <i class="bi bi-pencil"></i>
                </a>
                <button type="button" class="btn btn-outline-danger btn-sm"
                        title="Удалить"
                        onclick="deleteAccount({{ item.acc.id }}, '{{ item.acc.name | e }}')">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        </div>
    </div>
</div>
{% endfor %}
{% else %}
<div class="text-center text-muted py-5">
    <i class="bi bi-piggy-bank" style="font-size:3rem;opacity:.3"></i>
    <div class="mt-2">Накопительных счетов пока нет</div>
    <button type="button" class="btn grad-primary btn-sm mt-3"
            data-bs-toggle="modal" data-bs-target="#addAccountModal">
        <i class="bi bi-plus-lg me-1"></i>Создать первый счёт
    </button>
</div>
{% endif %}

{% if history %}
<div class="card shadow-sm border-0 mt-4">
    <div class="card-header bg-body fw-semibold border-0 pt-3">
        <i class="bi bi-clock-history text-primary me-2"></i>История операций
    </div>
    <ul class="list-group list-group-flush">
        {% for op in history %}
        <li class="list-group-item px-3 py-2">
            <div class="d-flex justify-content-between align-items-center gap-2">
                <div class="d-flex align-items-center gap-2">
                    <div class="rounded-circle d-flex align-items-center justify-content-center flex-shrink-0"
                         style="width:30px;height:30px;background:{% if op.type == 'deposit' %}#d1fae5{% else %}#fee2e2{% endif %}">
                        <i class="bi {% if op.type == 'deposit' %}bi-arrow-down text-success{% else %}bi-arrow-up text-danger{% endif %}"
                           style="font-size:.9rem"></i>
                    </div>
                    <div>
                        <div class="fw-semibold small">
                            {{ op.description or ('Пополнение' if op.type == 'deposit' else 'Снятие') }}
                        </div>
                        <span class="badge rounded-pill"
                              style="font-size:.7rem;background:{{ op.account_color }}22;
                                     color:{{ op.account_color }};border:1px solid {{ op.account_color }}55">
                            {{ op.account_name }}
                        </span>
                    </div>
                </div>
                <div class="text-end flex-shrink-0">
                    <div class="fw-semibold {% if op.type == 'deposit' %}text-danger{% else %}text-success{% endif %}">
                        {% if op.type == 'deposit' %}−{% else %}+{% endif %}{{ "%.2f"|format(op.amount) }} ₽
                    </div>
                    <div class="text-muted small">{{ op.date.strftime('%d.%m.%Y') }}</div>
                </div>
            </div>
        </li>
        {% endfor %}
    </ul>
</div>
{% endif %}
{% endblock %}

{% block modals %}
<!-- Добавить счёт -->
<div class="modal fade" id="addAccountModal" tabindex="-1">
    <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
            <div class="modal-header border-0">
                <h5 class="modal-title fw-semibold">
                    <i class="bi bi-piggy-bank text-primary me-2"></i>Новый счёт
                </h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body pt-0">
                <div class="mb-3">
                    <label class="form-label small fw-semibold">Название *</label>
                    <input type="text" id="accName" class="form-control" maxlength="100" placeholder="Отпуск, Машина…">
                </div>
                <div class="row g-3 mb-3">
                    <div class="col">
                        <label class="form-label small fw-semibold">Цвет</label>
                        <input type="color" id="accColor" class="form-control form-control-color w-100" value="#0d6efd">
                    </div>
                    <div class="col">
                        <label class="form-label small fw-semibold">Целевая сумма</label>
                        <input type="number" id="accTarget" class="form-control" min="1" placeholder="необязательно">
                    </div>
                </div>
                <div id="addAccError" class="text-danger small d-none"></div>
            </div>
            <div class="modal-footer border-0 pt-0">
                <button type="button" class="btn btn-outline-secondary btn-sm" data-bs-dismiss="modal">Отмена</button>
                <button type="button" class="btn grad-primary btn-sm" onclick="submitAddAccount()">Создать</button>
            </div>
        </div>
    </div>
</div>

<!-- Пополнить -->
<div class="modal fade" id="depositModal" tabindex="-1">
    <div class="modal-dialog modal-dialog-centered modal-sm">
        <div class="modal-content">
            <div class="modal-header border-0">
                <h6 class="modal-title fw-semibold">
                    <i class="bi bi-plus-circle text-success me-2"></i>Пополнить: <span id="depAccName"></span>
                </h6>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body pt-0">
                <div class="mb-3">
                    <label class="form-label small fw-semibold">Сумма *</label>
                    <input type="number" id="depAmount" class="form-control" min="0.01" step="0.01" placeholder="0.00">
                </div>
                <div class="mb-3">
                    <label class="form-label small fw-semibold">Дата *</label>
                    <input type="date" id="depDate" class="form-control">
                </div>
                <div class="mb-2">
                    <label class="form-label small fw-semibold">Описание</label>
                    <input type="text" id="depDesc" class="form-control" placeholder="необязательно">
                </div>
                <div id="depError" class="text-danger small d-none"></div>
            </div>
            <div class="modal-footer border-0 pt-0">
                <button type="button" class="btn btn-outline-secondary btn-sm" data-bs-dismiss="modal">Отмена</button>
                <button type="button" class="btn btn-success btn-sm" onclick="submitDeposit()">Пополнить</button>
            </div>
        </div>
    </div>
</div>

<!-- Снять -->
<div class="modal fade" id="withdrawModal" tabindex="-1">
    <div class="modal-dialog modal-dialog-centered modal-sm">
        <div class="modal-content">
            <div class="modal-header border-0">
                <h6 class="modal-title fw-semibold">
                    <i class="bi bi-dash-circle text-danger me-2"></i>Снять: <span id="witAccName"></span>
                </h6>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body pt-0">
                <div class="mb-1">
                    <label class="form-label small fw-semibold">Сумма *</label>
                    <input type="number" id="witAmount" class="form-control" min="0.01" step="0.01" placeholder="0.00">
                    <div class="text-muted small mt-1">Доступно: <span id="witBalance"></span> ₽</div>
                </div>
                <div class="mb-3 mt-3">
                    <label class="form-label small fw-semibold">Дата *</label>
                    <input type="date" id="witDate" class="form-control">
                </div>
                <div class="mb-2">
                    <label class="form-label small fw-semibold">Описание</label>
                    <input type="text" id="witDesc" class="form-control" placeholder="необязательно">
                </div>
                <div id="witError" class="text-danger small d-none"></div>
            </div>
            <div class="modal-footer border-0 pt-0">
                <button type="button" class="btn btn-outline-secondary btn-sm" data-bs-dismiss="modal">Отмена</button>
                <button type="button" class="btn btn-danger btn-sm" onclick="submitWithdraw()">Снять</button>
            </div>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
const todayStr = '{{ today.isoformat() }}';
let _depAccId = null, _witAccId = null;

async function submitAddAccount() {
    const name   = document.getElementById('accName').value.trim();
    const color  = document.getElementById('accColor').value;
    const target = document.getElementById('accTarget').value.trim();
    const errEl  = document.getElementById('addAccError');
    errEl.classList.add('d-none');
    const body = {name, color};
    if (target) body.target_amount = parseFloat(target);
    const res = await fetch('/savings/add', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
        body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) { errEl.textContent = data.error; errEl.classList.remove('d-none'); return; }
    location.reload();
}

function openDepositModal(accId, name, balance) {
    _depAccId = accId;
    document.getElementById('depAccName').textContent = name;
    document.getElementById('depAmount').value = '';
    document.getElementById('depDate').value = todayStr;
    document.getElementById('depDesc').value = '';
    document.getElementById('depError').classList.add('d-none');
    bootstrap.Modal.getOrCreateInstance(document.getElementById('depositModal')).show();
}

async function submitDeposit() {
    const amount = document.getElementById('depAmount').value;
    const date   = document.getElementById('depDate').value;
    const desc   = document.getElementById('depDesc').value.trim();
    const errEl  = document.getElementById('depError');
    errEl.classList.add('d-none');
    const res = await fetch(`/savings/${_depAccId}/deposit`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
        body: JSON.stringify({amount: parseFloat(amount), date, description: desc}),
    });
    const data = await res.json();
    if (!res.ok) { errEl.textContent = data.error; errEl.classList.remove('d-none'); return; }
    location.reload();
}

function openWithdrawModal(accId, name, balance) {
    _witAccId = accId;
    document.getElementById('witAccName').textContent = name;
    document.getElementById('witBalance').textContent = balance.toFixed(2);
    document.getElementById('witAmount').value = '';
    document.getElementById('witDate').value = todayStr;
    document.getElementById('witDesc').value = '';
    document.getElementById('witError').classList.add('d-none');
    bootstrap.Modal.getOrCreateInstance(document.getElementById('withdrawModal')).show();
}

async function submitWithdraw() {
    const amount = document.getElementById('witAmount').value;
    const date   = document.getElementById('witDate').value;
    const desc   = document.getElementById('witDesc').value.trim();
    const errEl  = document.getElementById('witError');
    errEl.classList.add('d-none');
    const res = await fetch(`/savings/${_witAccId}/withdraw`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
        body: JSON.stringify({amount: parseFloat(amount), date, description: desc}),
    });
    const data = await res.json();
    if (!res.ok) { errEl.textContent = data.error; errEl.classList.remove('d-none'); return; }
    location.reload();
}

async function deleteAccount(accId, name) {
    if (!confirm(`Удалить счёт «${name}»? Это действие нельзя отменить.`)) return;
    const res = await fetch(`/savings/${accId}`, {
        method: 'DELETE',
        headers: {'X-CSRFToken': csrfToken},
    });
    const data = await res.json();
    if (!res.ok) { alert(data.error); return; }
    location.reload();
}
</script>
{% endblock %}
```

- [ ] **Step 5: Create `templates/savings/form.html`**

```html
{% extends 'base.html' %}
{% block title %}Редактировать счёт{% endblock %}

{% block content %}
<div class="row justify-content-center">
    <div class="col-md-6">
        <div class="card shadow-sm border-0">
            <div class="card-header bg-body fw-semibold border-0 pt-3">
                <i class="bi bi-pencil text-primary me-2"></i>Редактировать счёт
            </div>
            <div class="card-body">
                <form method="post">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <div class="mb-3">
                        <label class="form-label fw-semibold">Название *</label>
                        <input type="text" name="name" class="form-control"
                               maxlength="100" value="{{ acc.name }}" required>
                    </div>
                    <div class="row g-3 mb-3">
                        <div class="col">
                            <label class="form-label fw-semibold">Цвет</label>
                            <input type="color" name="color" class="form-control form-control-color w-100"
                                   value="{{ acc.color }}">
                        </div>
                        <div class="col">
                            <label class="form-label fw-semibold">Иконка</label>
                            <input type="text" name="icon" class="form-control"
                                   value="{{ acc.icon }}" placeholder="bi-piggy-bank">
                        </div>
                    </div>
                    <div class="mb-4">
                        <label class="form-label fw-semibold">Целевая сумма</label>
                        <input type="number" name="target_amount" class="form-control"
                               min="1" step="0.01"
                               value="{{ acc.target_amount|float if acc.target_amount else '' }}"
                               placeholder="необязательно">
                    </div>
                    <div class="d-flex gap-2">
                        <button type="submit" class="btn grad-primary btn-sm">Сохранить</button>
                        <a href="{{ url_for('savings_list') }}" class="btn btn-outline-secondary btn-sm">Отмена</a>
                    </div>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 6: Add «Накопления» nav link to `templates/base.html`**

After the `Бюджет` nav-item (around line ~73), add:

```html
                <li class="nav-item">
                    <a class="nav-link {% if 'savings' in request.endpoint %}active{% endif %}"
                       href="{{ url_for('savings_list') }}">
                        <i class="bi bi-piggy-bank me-1"></i>Накопления
                    </a>
                </li>
```

- [ ] **Step 7: Run CRUD tests — must PASS**

```bash
python -m pytest tests/test_savings.py -v 2>&1 | tail -20
```

Expected: все тесты `PASSED`

- [ ] **Step 8: Commit**

```bash
git add app.py templates/savings/ templates/base.html
git commit -m "feat: add savings accounts CRUD routes and templates"
```

---

## Task 5: Deposit + withdraw routes + tests

**Files:**
- Modify: `app.py`
- Modify: `tests/test_savings.py`

- [ ] **Step 1: Add deposit/withdraw tests**

Append to `tests/test_savings.py`:

```python
def test_deposit_creates_expense_and_updates_balance(account):
    client, uid, acc_id = account
    today = datetime.date.today().isoformat()
    resp = client.post(f'/savings/{acc_id}/deposit',
                       json={'amount': 20000, 'date': today, 'description': 'Первый взнос'},
                       content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True
    assert data['balance'] == 20000.0

    with flask_app.app_context():
        exp = Expense.query.filter_by(savings_account_id=acc_id).first()
        assert exp is not None
        assert float(exp.amount) == 20000.0
        assert exp.is_spent is True
        assert exp.is_planned is False


def test_withdraw_creates_income_and_updates_balance(account):
    client, uid, acc_id = account
    today = datetime.date.today().isoformat()
    # Deposit first
    client.post(f'/savings/{acc_id}/deposit',
                json={'amount': 15000, 'date': today},
                content_type='application/json')
    # Withdraw
    resp = client.post(f'/savings/{acc_id}/withdraw',
                       json={'amount': 5000, 'date': today},
                       content_type='application/json')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['balance'] == 10000.0

    with flask_app.app_context():
        inc = Income.query.filter_by(savings_account_id=acc_id).first()
        assert inc is not None
        assert float(inc.amount) == 5000.0


def test_withdraw_overdraft_rejected(account):
    client, uid, acc_id = account
    today = datetime.date.today().isoformat()
    client.post(f'/savings/{acc_id}/deposit',
                json={'amount': 1000, 'date': today},
                content_type='application/json')
    resp = client.post(f'/savings/{acc_id}/withdraw',
                       json={'amount': 9999, 'date': today},
                       content_type='application/json')
    assert resp.status_code == 400
    assert 'Недостаточно средств' in resp.get_json()['error']


def test_deposit_invalid_amount_rejected(account):
    client, uid, acc_id = account
    resp = client.post(f'/savings/{acc_id}/deposit',
                       json={'amount': -100, 'date': '2026-04-24'},
                       content_type='application/json')
    assert resp.status_code == 400


def test_deposit_other_user_returns_404(account):
    client, uid, acc_id = account
    with flask_app.app_context():
        u2 = User(username='other2', email='other2@ex.com', role='user')
        u2.set_password('pass')
        db.session.add(u2)
        db.session.commit()
    other = flask_app.test_client()
    other.post('/login', data={'username': 'other2', 'password': 'pass', 'website': ''})
    resp = other.post(f'/savings/{acc_id}/deposit',
                      json={'amount': 100, 'date': '2026-04-24'},
                      content_type='application/json')
    assert resp.status_code == 404
```

- [ ] **Step 2: Run deposit/withdraw tests — must FAIL**

```bash
python -m pytest tests/test_savings.py::test_deposit_creates_expense_and_updates_balance tests/test_savings.py::test_withdraw_creates_income_and_updates_balance -v 2>&1 | tail -15
```

Expected: `404 NOT FOUND`

- [ ] **Step 3: Add deposit and withdraw routes to app.py**

Append after `savings_delete` route:

```python
@app.route('/savings/<int:acc_id>/deposit', methods=['POST'])
@login_required
@ban_check
def savings_deposit(acc_id):
    acc = SavingsAccount.query.filter_by(id=acc_id, user_id=current_user.id).first_or_404()
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400
    try:
        amount = float(data['amount'])
        if amount <= 0:
            raise ValueError
    except (ValueError, KeyError, TypeError):
        return jsonify({'error': 'Неверная сумма'}), 400
    try:
        txn_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
    except (ValueError, KeyError, TypeError):
        return jsonify({'error': 'Неверная дата'}), 400
    description = (data.get('description') or '').strip() or f'Пополнение: {acc.name}'
    cat = get_savings_category()
    exp = Expense(
        user_id=current_user.id,
        category_id=cat.id,
        savings_account_id=acc_id,
        amount=amount,
        description=description,
        expense_date=txn_date,
        is_planned=False,
        is_spent=True,
    )
    db.session.add(exp)
    try:
        db.session.commit()
        return jsonify({'ok': True, 'balance': get_account_balance(acc_id)})
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Ошибка сохранения'}), 500


@app.route('/savings/<int:acc_id>/withdraw', methods=['POST'])
@login_required
@ban_check
def savings_withdraw(acc_id):
    acc = SavingsAccount.query.filter_by(id=acc_id, user_id=current_user.id).first_or_404()
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400
    try:
        amount = float(data['amount'])
        if amount <= 0:
            raise ValueError
    except (ValueError, KeyError, TypeError):
        return jsonify({'error': 'Неверная сумма'}), 400
    try:
        txn_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
    except (ValueError, KeyError, TypeError):
        return jsonify({'error': 'Неверная дата'}), 400
    balance = get_account_balance(acc_id)
    if amount > balance:
        return jsonify({'error': f'Недостаточно средств. Баланс: {balance:.2f} ₽'}), 400
    description = (data.get('description') or '').strip() or None
    inc = Income(
        user_id=current_user.id,
        savings_account_id=acc_id,
        source=acc.name,
        amount=amount,
        description=description,
        income_date=txn_date,
    )
    db.session.add(inc)
    try:
        db.session.commit()
        return jsonify({'ok': True, 'balance': get_account_balance(acc_id)})
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Ошибка сохранения'}), 500
```

- [ ] **Step 4: Run all savings tests — must PASS**

```bash
python -m pytest tests/test_savings.py -v 2>&1 | tail -25
```

Expected: все тесты `PASSED`

- [ ] **Step 5: Run full test suite — no regressions**

```bash
python -m pytest tests/ -v 2>&1 | tail -30
```

Expected: все тесты `PASSED`

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_savings.py
git commit -m "feat: add savings deposit and withdraw routes"
```

---

## Task 6: Dashboard savings block

**Files:**
- Modify: `app.py` (index route)
- Modify: `templates/index.html`

- [ ] **Step 1: Update `index()` route to pass savings_data**

In `app.py`, inside the `index()` function, after the `can_copy` calculation, add:

```python
    savings_accounts = SavingsAccount.query.filter_by(
        user_id=uid, is_active=True
    ).order_by(SavingsAccount.created_at.asc()).all()
    savings_data = []
    for acc in savings_accounts:
        bal = get_account_balance(acc.id)
        pct = None
        if acc.target_amount and float(acc.target_amount) > 0:
            pct = min(round(bal / float(acc.target_amount) * 100, 1), 100.0)
        savings_data.append({'acc': acc, 'balance': bal, 'pct': pct})
```

Add `savings_data=savings_data` to the `return render_template('index.html', ...)` call.

- [ ] **Step 2: Add savings block to `templates/index.html`**

After the closing `</div>` of the `row g-3 mb-4 summary-cards` section (after the 4 cards, around line ~139), insert:

```html
{% if savings_data %}
<div class="card shadow-sm border-0 mb-4">
    <div class="card-header bg-body fw-semibold border-0 pt-3 d-flex justify-content-between align-items-center">
        <span><i class="bi bi-piggy-bank-fill text-primary me-2"></i>Накопления</span>
        <a href="{{ url_for('savings_list') }}" class="small">все счета →</a>
    </div>
    <div class="card-body">
        <div class="row g-3">
            {% for item in savings_data %}
            <div class="col-sm-6 col-lg-4">
                <div class="border rounded-3 p-3 h-100">
                    <div class="d-flex align-items-center gap-2 mb-2">
                        <div class="rounded-2 d-flex align-items-center justify-content-center flex-shrink-0"
                             style="width:32px;height:32px;background:{{ item.acc.color }}22">
                            <i class="bi {{ item.acc.icon }}" style="color:{{ item.acc.color }}"></i>
                        </div>
                        <span class="fw-semibold text-truncate">{{ item.acc.name }}</span>
                    </div>
                    <div class="fw-bold fs-5 text-success mb-1">{{ "%.2f"|format(item.balance) }} ₽</div>
                    {% if item.acc.target_amount and item.pct is not none %}
                    <div class="text-muted small mb-1">
                        из {{ "%.0f"|format(item.acc.target_amount|float) }} ₽ — {{ item.pct }}%
                    </div>
                    <div class="progress mb-2" style="height:5px;border-radius:4px">
                        <div class="progress-bar" style="width:{{ item.pct }}%;background:{{ item.acc.color }}"></div>
                    </div>
                    {% endif %}
                    <div class="d-flex gap-1 mt-2">
                        <button type="button" class="btn btn-outline-success btn-sm flex-fill"
                                style="font-size:.75rem"
                                onclick="openSavingsDepositModal({{ item.acc.id }}, '{{ item.acc.name | e }}')">
                            <i class="bi bi-plus"></i> Пополнить
                        </button>
                        <button type="button" class="btn btn-outline-danger btn-sm flex-fill"
                                style="font-size:.75rem"
                                onclick="openSavingsWithdrawModal({{ item.acc.id }}, '{{ item.acc.name | e }}', {{ item.balance }})">
                            <i class="bi bi-dash"></i> Снять
                        </button>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
</div>
{% endif %}
```

- [ ] **Step 3: Add deposit/withdraw modals and JS to `{% block modals %}` in `index.html`**

Add before the closing of `{% block modals %}` (after the paymentDaysModal):

```html
<!-- Savings deposit modal (dashboard) -->
<div class="modal fade" id="dashDepositModal" tabindex="-1">
    <div class="modal-dialog modal-dialog-centered modal-sm">
        <div class="modal-content">
            <div class="modal-header border-0">
                <h6 class="modal-title fw-semibold">
                    <i class="bi bi-plus-circle text-success me-1"></i>Пополнить: <span id="dashDepName"></span>
                </h6>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body pt-0">
                <div class="mb-3">
                    <label class="form-label small fw-semibold">Сумма *</label>
                    <input type="number" id="dashDepAmount" class="form-control" min="0.01" step="0.01">
                </div>
                <div class="mb-2">
                    <label class="form-label small fw-semibold">Дата *</label>
                    <input type="date" id="dashDepDate" class="form-control">
                </div>
                <div id="dashDepError" class="text-danger small d-none"></div>
            </div>
            <div class="modal-footer border-0 pt-0">
                <button class="btn btn-outline-secondary btn-sm" data-bs-dismiss="modal">Отмена</button>
                <button class="btn btn-success btn-sm" onclick="submitDashDeposit()">Пополнить</button>
            </div>
        </div>
    </div>
</div>

<!-- Savings withdraw modal (dashboard) -->
<div class="modal fade" id="dashWithdrawModal" tabindex="-1">
    <div class="modal-dialog modal-dialog-centered modal-sm">
        <div class="modal-content">
            <div class="modal-header border-0">
                <h6 class="modal-title fw-semibold">
                    <i class="bi bi-dash-circle text-danger me-1"></i>Снять: <span id="dashWitName"></span>
                </h6>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body pt-0">
                <div class="mb-3">
                    <label class="form-label small fw-semibold">Сумма *</label>
                    <input type="number" id="dashWitAmount" class="form-control" min="0.01" step="0.01">
                    <div class="text-muted small mt-1">Доступно: <span id="dashWitBalance"></span> ₽</div>
                </div>
                <div class="mb-2">
                    <label class="form-label small fw-semibold">Дата *</label>
                    <input type="date" id="dashWitDate" class="form-control">
                </div>
                <div id="dashWitError" class="text-danger small d-none"></div>
            </div>
            <div class="modal-footer border-0 pt-0">
                <button class="btn btn-outline-secondary btn-sm" data-bs-dismiss="modal">Отмена</button>
                <button class="btn btn-danger btn-sm" onclick="submitDashWithdraw()">Снять</button>
            </div>
        </div>
    </div>
</div>
```

Add to `{% block scripts %}` in `index.html`, before the closing `</script>`:

```javascript
// ── Savings modals on dashboard ───────────────────────────────────
let _dashDepAccId = null, _dashWitAccId = null;
const _todayIso = new Date().toISOString().slice(0,10);

function openSavingsDepositModal(accId, name) {
    _dashDepAccId = accId;
    document.getElementById('dashDepName').textContent = name;
    document.getElementById('dashDepAmount').value = '';
    document.getElementById('dashDepDate').value = _todayIso;
    document.getElementById('dashDepError').classList.add('d-none');
    bootstrap.Modal.getOrCreateInstance(document.getElementById('dashDepositModal')).show();
}

async function submitDashDeposit() {
    const amount = document.getElementById('dashDepAmount').value;
    const date   = document.getElementById('dashDepDate').value;
    const errEl  = document.getElementById('dashDepError');
    errEl.classList.add('d-none');
    const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
    const res = await fetch(`/savings/${_dashDepAccId}/deposit`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
        body: JSON.stringify({amount: parseFloat(amount), date}),
    });
    const data = await res.json();
    if (!res.ok) { errEl.textContent = data.error; errEl.classList.remove('d-none'); return; }
    location.reload();
}

function openSavingsWithdrawModal(accId, name, balance) {
    _dashWitAccId = accId;
    document.getElementById('dashWitName').textContent = name;
    document.getElementById('dashWitBalance').textContent = balance.toFixed(2);
    document.getElementById('dashWitAmount').value = '';
    document.getElementById('dashWitDate').value = _todayIso;
    document.getElementById('dashWitError').classList.add('d-none');
    bootstrap.Modal.getOrCreateInstance(document.getElementById('dashWithdrawModal')).show();
}

async function submitDashWithdraw() {
    const amount = document.getElementById('dashWitAmount').value;
    const date   = document.getElementById('dashWitDate').value;
    const errEl  = document.getElementById('dashWitError');
    errEl.classList.add('d-none');
    const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
    const res = await fetch(`/savings/${_dashWitAccId}/withdraw`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
        body: JSON.stringify({amount: parseFloat(amount), date}),
    });
    const data = await res.json();
    if (!res.ok) { errEl.textContent = data.error; errEl.classList.remove('d-none'); return; }
    location.reload();
}
```

- [ ] **Step 4: Run full test suite — no regressions**

```bash
python -m pytest tests/ -v 2>&1 | tail -30
```

Expected: все тесты `PASSED`

- [ ] **Step 5: Commit**

```bash
git add app.py templates/index.html
git commit -m "feat: add savings block to main dashboard"
```

---

## Task 7: Savings badges in expense and income lists

**Files:**
- Modify: `templates/expenses/list.html`
- Modify: `templates/income/list.html`

- [ ] **Step 1: Add savings badge to `templates/expenses/list.html`**

In the expense row block, find the badges section (around line ~593–602 where `is_planned` and `is_spent` badges are rendered). After the `{% if not exp.is_spent %}` badge, add:

```html
                {% if exp.savings_account %}
                    <span class="badge ms-1"
                          style="background:{{ exp.savings_account.color }}22;
                                 color:{{ exp.savings_account.color }};
                                 border:1px solid {{ exp.savings_account.color }}55;
                                 font-size:.7rem">
                        <i class="bi bi-piggy-bank me-1"></i>{{ exp.savings_account.name }}
                    </span>
                {% endif %}
```

- [ ] **Step 2: Add savings badge to `templates/income/list.html`**

In the income row block, find where `inc.source` is displayed (around line ~150). After the source line, add:

```html
                {% if inc.savings_account %}
                    <span class="badge ms-1"
                          style="background:{{ inc.savings_account.color }}22;
                                 color:{{ inc.savings_account.color }};
                                 border:1px solid {{ inc.savings_account.color }}55;
                                 font-size:.7rem">
                        <i class="bi bi-piggy-bank me-1"></i>{{ inc.savings_account.name }}
                    </span>
                {% endif %}
```

- [ ] **Step 3: Run full test suite — no regressions**

```bash
python -m pytest tests/ -v 2>&1 | tail -30
```

Expected: все тесты `PASSED`

- [ ] **Step 4: Commit**

```bash
git add templates/expenses/list.html templates/income/list.html
git commit -m "feat: add savings account badge to expense and income lists"
```

---

## Self-Review Notes

**Spec coverage check:**
- ✅ SavingsAccount model с name, color, icon, target_amount, is_active
- ✅ Пополнение → Expense со savings_account_id
- ✅ Снятие → Income со savings_account_id
- ✅ Баланс счёта через get_account_balance
- ✅ Системная категория «Накопления» (seed + get_savings_category)
- ✅ Маршруты: GET /savings, POST /savings/add, GET/POST /savings/<id>/edit, DELETE /savings/<id>, POST /savings/<id>/deposit, POST /savings/<id>/withdraw
- ✅ Валидация: снятие > баланса → 400; удаление с транзакциями → 409
- ✅ Dashboard блок накоплений с прогресс-барами
- ✅ Отдельная страница /savings с историей
- ✅ Бейджи в списках расходов и доходов
- ✅ DB migration в app.app_context() блоке

**Spec formula correction:**
В спеке формула баланса указана как `SUM(Income) - SUM(Expense)`, но это инвертировано. Правильно: `balance = SUM(Expense WHERE savings_account_id) - SUM(Income WHERE savings_account_id)`, потому что депозит создаёт Expense (добавляет к балансу счёта), снятие создаёт Income (уменьшает баланс счёта). Реализация использует корректную формулу.
