# Search & Budget Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add client-side expense search and configurable budget-threshold alerts (inline icons + toast).

**Architecture:** Two independent features sharing one migration (new `budget_alert_pct` column on `User`). Search is pure frontend JS. Budget alerts add a context processor, a new route, and template changes to dashboard + base + profile.

**Tech Stack:** Flask/SQLAlchemy (backend), Bootstrap 5 toasts (alerts), vanilla JS with debounce (search), Jinja2 templates.

---

## File Map

| File | Change |
|------|--------|
| `app.py` | Add `budget_alert_pct` to `User`; add `alert_map` in `index()`; add `inject_budget_alerts` context processor; add `profile_budget_alert_pct` route |
| `static/css/style.css` | Add `.alert-warning-row` / `.alert-exceeded-row` styles |
| `templates/index.html` | Alert icons + row highlights in category list |
| `templates/base.html` | Budget alert toast HTML + JS |
| `templates/profile.html` | Threshold form card |
| `templates/expenses/list.html` | Search input in filter row + JS + total recalculation |
| `tests/test_budget_alerts.py` | New test file |

---

## Task 1: Add `budget_alert_pct` to User model

**Files:**
- Modify: `app.py:123-125` (User model fields, after `advance_day`)

- [ ] **Step 1: Add the column**

In `app.py`, after line `advance_day = db.Column(db.Integer, nullable=True)` (≈ line 123), add:

```python
    budget_alert_pct = db.Column(db.Integer, nullable=False, default=80)
```

- [ ] **Step 2: Apply migration for SQLite dev DB**

```bash
cd /Users/k1n4_l0v3d/Desktop/expence_tracker-main
source venv/bin/activate
python - <<'EOF'
from sqlalchemy import text
from app import app, db
with app.app_context():
    db.create_all()
    # SQLite doesn't auto-add columns to existing tables via create_all.
    # Run the ALTER manually:
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN budget_alert_pct INTEGER NOT NULL DEFAULT 80"))
            conn.commit()
        print("Column added.")
    except Exception as e:
        print(f"Skipped (probably exists): {e}")
EOF
```

Expected output: `Column added.` (or skip message if already present)

- [ ] **Step 3: Verify tests still pass**

```bash
pytest tests/ -q
```

Expected: all existing tests pass (no failures).

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: add budget_alert_pct field to User model"
```

---

## Task 2: Build `alert_map` in `index()` route

**Files:**
- Modify: `app.py` — `index()` function (~line 1214)
- Test: `tests/test_budget_alerts.py` (create)

- [ ] **Step 1: Write failing test**

Create `tests/test_budget_alerts.py`:

```python
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
        cat_id = cat.id

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
    assert b'alert-exceeded-row' in resp.data or b'\xd0\xbf\xd1\x80\xd0\xb5\xd0\xb2\xd1\x8b\xd1\x88\xd0\xb5\xd0\xbd' in resp.data  # "превышен" in UTF-8
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/test_budget_alerts.py -v
```

Expected: FAIL — `alert_map` not yet passed to template.

- [ ] **Step 3: Add `alert_map` to `index()`**

In `app.py`, inside `index()`, after the line `can_copy = current_empty and (prev_has_expenses or prev_has_income)` add:

```python
    # Budget alert map for current view month
    alert_pct = current_user.budget_alert_pct
    alert_map = {}
    for row in summary:
        budget = budget_map.get(row.id, 0)
        if budget <= 0:
            continue
        spent = float(row.total or 0)
        pct   = spent / budget * 100
        if spent > budget:
            alert_map[row.id] = 'exceeded'
        elif pct >= alert_pct:
            alert_map[row.id] = 'warning'
```

Then add `alert_map=alert_map,` to the `render_template(...)` call at the end of `index()`.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_budget_alerts.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_budget_alerts.py
git commit -m "feat: build alert_map in index() and add budget alert tests"
```

---

## Task 3: Add `inject_budget_alerts` context processor

**Files:**
- Modify: `app.py` — after `inject_reminders` context processor (~line 1455)
- Test: `tests/test_budget_alerts.py` (append)

- [ ] **Step 1: Write failing test**

Append to `tests/test_budget_alerts.py`:

```python
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
    # Toast rendered when budget_alerts is non-empty
    assert b'budget-alert-toast' in resp.data
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/test_budget_alerts.py::test_inject_budget_alerts_returns_alerts -v
```

Expected: FAIL — `budget-alert-toast` not yet in templates.

- [ ] **Step 3: Add context processor to `app.py`**

After the `inject_reminders` function (after line ≈1455), add:

```python
@app.context_processor
def inject_budget_alerts():
    if not current_user.is_authenticated:
        return {'budget_alerts': []}
    today   = date.today()
    summary = get_monthly_summary(current_user.id, today.year, today.month)
    bmap    = get_budget_map(current_user.id, today.year, today.month)
    threshold = current_user.budget_alert_pct
    alerts = []
    for row in summary:
        budget = bmap.get(row.id, 0)
        if budget <= 0:
            continue
        spent = float(row.total or 0)
        pct   = spent / budget * 100
        if spent > budget:
            alerts.append({'name': row.name, 'icon': row.icon,
                           'color': row.color, 'level': 'exceeded',
                           'pct': int(pct)})
        elif pct >= threshold:
            alerts.append({'name': row.name, 'icon': row.icon,
                           'color': row.color, 'level': 'warning',
                           'pct': int(pct)})
    return {'budget_alerts': alerts}
```

- [ ] **Step 4: Add toast HTML + JS to `templates/base.html`**

In `templates/base.html`, find the block ending `{% endif %}` after the reminders toast container (after line ≈491). Insert immediately after:

```html
{% if budget_alerts %}
<div class="toast-container position-fixed bottom-0 end-0 p-3" style="z-index:1100">
  <div class="toast" id="budget-alert-toast" role="alert" data-bs-autohide="true" data-bs-delay="8000">
    <div class="toast-header">
      <strong class="me-auto"><i class="bi bi-wallet2 me-1"></i>Бюджет</strong>
      <button type="button" class="btn-close" data-bs-dismiss="toast" aria-label="Закрыть"></button>
    </div>
    <div class="toast-body">
      {% for a in budget_alerts %}
      <div>
        {% if a.level == 'exceeded' %}🔴{% else %}⚠️{% endif %}
        <strong>{{ a.name }}</strong> —
        {% if a.level == 'exceeded' %}превышен{% else %}{{ a.pct }}% бюджета{% endif %}
      </div>
      {% endfor %}
    </div>
  </div>
</div>
<script>
(function() {
    var t = document.getElementById('budget-alert-toast');
    if (t && !sessionStorage.getItem('budget_toast_shown')) {
        sessionStorage.setItem('budget_toast_shown', '1');
        new bootstrap.Toast(t).show();
    }
})();
</script>
{% endif %}
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_budget_alerts.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app.py templates/base.html
git commit -m "feat: add inject_budget_alerts context processor and toast"
```

---

## Task 4: Profile route to save threshold

**Files:**
- Modify: `app.py` — add route after `profile_clear_data` (~line 1074)
- Modify: `templates/profile.html`
- Test: `tests/test_budget_alerts.py` (append)

- [ ] **Step 1: Write failing test**

Append to `tests/test_budget_alerts.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_budget_alerts.py::test_profile_budget_alert_pct_saves tests/test_budget_alerts.py::test_profile_budget_alert_pct_rejects_invalid -v
```

Expected: FAIL — route does not exist (404).

- [ ] **Step 3: Add route to `app.py`**

After `profile_clear_data` route (after line ≈1074), add:

```python
@app.route('/profile/budget-alert-pct', methods=['POST'])
@login_required
@ban_check
def profile_budget_alert_pct():
    alert_pct = request.form.get('budget_alert_pct', type=int)
    if alert_pct is None or not (1 <= alert_pct <= 100):
        flash('Порог должен быть от 1 до 100.', 'danger')
    else:
        current_user.budget_alert_pct = alert_pct
        db.session.commit()
        flash('Настройки сохранены.', 'success')
    return redirect(url_for('profile'))
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_budget_alerts.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Add form to `templates/profile.html`**

After the "Сменить пароль" card (after the closing `</div>` of that card, ≈ line 129), insert a new card:

```html
<!-- Настройки уведомлений -->
<div class="card shadow-sm border-0 mt-4">
    <div class="card-header border-0 fw-semibold pt-3">
        <i class="bi bi-bell me-2 text-primary"></i>Уведомления
    </div>
    <div class="card-body">
        <form method="post" action="{{ url_for('profile_budget_alert_pct') }}">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <div class="mb-3">
                <label class="form-label fw-semibold">Порог бюджетного алерта (%)</label>
                <input type="number" name="budget_alert_pct" class="form-control"
                       min="1" max="100" value="{{ current_user.budget_alert_pct }}">
                <div class="form-text">
                    Уведомление появится, когда расходы категории достигнут этого % от лимита
                </div>
            </div>
            <button type="submit" class="btn grad-primary btn-sm">
                <i class="bi bi-check-lg me-1"></i>Сохранить
            </button>
        </form>
    </div>
</div>
```

- [ ] **Step 6: Commit**

```bash
git add app.py templates/profile.html tests/test_budget_alerts.py
git commit -m "feat: add profile route and form for budget alert threshold"
```

---

## Task 5: Alert icons + row highlight in dashboard

**Files:**
- Modify: `static/css/style.css` (append)
- Modify: `templates/index.html` (category list, ≈ lines 211–230)

- [ ] **Step 1: Add CSS to `static/css/style.css`**

Append at the end of the file:

```css
/* Budget alert row highlights */
.alert-warning-row  { background: rgba(255, 193, 7, 0.08) !important; }
.alert-exceeded-row { background: rgba(220, 53, 69, 0.08) !important; }
[data-bs-theme="dark"] .alert-warning-row  { background: rgba(255, 193, 7, 0.10) !important; }
[data-bs-theme="dark"] .alert-exceeded-row { background: rgba(220, 53, 69, 0.10) !important; }
```

- [ ] **Step 2: Update category list in `templates/index.html`**

Find the `<li class="list-group-item px-3 py-3">` line inside the `{% for row in summary %}` loop (≈ line 211). Replace it with:

```html
<li class="list-group-item px-3 py-3{% if alert_map.get(row.id) == 'warning' %} alert-warning-row{% elif alert_map.get(row.id) == 'exceeded' %} alert-exceeded-row{% endif %}">
```

Then find the `<span>` containing the category icon and name (≈ line 213):

```html
                        <span>
                                <i class="bi {{ row.icon }} me-2" style="color:{{ row.color }}"></i>
                                <strong>{{ row.name }}</strong>
                            </span>
```

Replace with:

```html
                        <span>
                                <i class="bi {{ row.icon }} me-2" style="color:{{ row.color }}"></i>
                                <strong>{{ row.name }}</strong>
                                {% if alert_map.get(row.id) == 'warning' %}
                                    <span class="ms-1 text-warning" style="font-size:.8rem"
                                          title="Использовано {{ (spent / budget * 100)|int }}% бюджета">⚠️</span>
                                {% elif alert_map.get(row.id) == 'exceeded' %}
                                    <span class="ms-1 text-danger" style="font-size:.8rem"
                                          title="Бюджет превышен">🔴</span>
                                {% endif %}
                            </span>
```

Note: `spent` and `budget` are already set via `{% set spent = row.total|float %}` and `{% set budget = budget_map.get(row.id, 0) %}` earlier in the loop.

- [ ] **Step 3: Verify template renders**

```bash
cd /Users/k1n4_l0v3d/Desktop/expence_tracker-main && source venv/bin/activate
python -c "from app import app, db; app.config['TESTING']=True"
echo "Import OK"
```

Expected: `Import OK` with no errors.

- [ ] **Step 4: Commit**

```bash
git add static/css/style.css templates/index.html
git commit -m "feat: add budget alert icons and row highlights to dashboard"
```

---

## Task 6: Client-side expense search

**Files:**
- Modify: `templates/expenses/list.html`

- [ ] **Step 1: Add search input to filter form**

In `templates/expenses/list.html`, find the line with the category select ending `onchange="this.form.submit()">` (≈ line 28). After the closing `</select>` of the category select, add:

```html
    <div class="input-group input-group-sm" style="width:200px">
        <span class="input-group-text border-end-0 bg-transparent">
            <i class="bi bi-search text-muted"></i>
        </span>
        <input type="text" id="expenseSearch" class="form-control border-start-0"
               placeholder="Поиск..." autocomplete="off"
               style="padding-left:0">
        <span id="searchCount" class="input-group-text d-none"
              style="font-size:.75rem;white-space:nowrap;color:var(--bs-secondary-color)"></span>
    </div>
```

- [ ] **Step 2: Add `filter-total-amount` class to the total span**

Find the итого row at the bottom (≈ line 681):

```html
        <span class="fw-bold">{{ "%.2f"|format(expenses|sum(attribute='amount')|float) }} ₽</span>
```

Replace with:

```html
        <span class="fw-bold filter-total-amount">{{ "%.2f"|format(expenses|sum(attribute='amount')|float) }} ₽</span>
```

- [ ] **Step 3: Add search JS**

Inside the existing `<script>` block in the file (before the closing `</script>` tag), add:

```javascript
// ── Поиск по расходам (клиентский) ────────────────────────────────
(function () {
    var input   = document.getElementById('expenseSearch');
    if (!input) return;
    var countEl = document.getElementById('searchCount');
    var timer;

    function applySearch() {
        var q = input.value.trim().toLowerCase();
        var allCards = document.querySelectorAll('.record-card');
        var visible  = 0;
        var total    = allCards.length;

        allCards.forEach(function (card) {
            if (!q) {
                card.style.display = '';
                visible++;
                return;
            }
            var desc     = (card.querySelector('.fw-semibold')?.textContent  || '').toLowerCase();
            var notes    = (card.querySelector('.fst-italic')?.textContent   || '').toLowerCase();
            var category = (card.querySelector('.badge')?.textContent        || '').toLowerCase();
            var match    = desc.includes(q) || notes.includes(q) || category.includes(q);
            card.style.display = match ? '' : 'none';
            if (match) visible++;
        });

        // Счётчик
        if (q) {
            countEl.textContent = visible + ' из ' + total;
            countEl.classList.remove('d-none');
        } else {
            countEl.classList.add('d-none');
        }

        // Пересчёт суммы
        var totalEl = document.querySelector('.filter-total-amount');
        if (totalEl) {
            var sum = 0;
            document.querySelectorAll('.record-card').forEach(function (card) {
                if (card.style.display !== 'none') {
                    var amtEl = card.querySelector('.fw-bold.fs-6');
                    if (amtEl) {
                        var val = parseFloat(amtEl.textContent.replace(/[^\d.,]/g, '').replace(',', '.')) || 0;
                        sum += val;
                    }
                }
            });
            totalEl.textContent = sum.toFixed(2) + ' ₽';
        }
    }

    input.addEventListener('input', function () {
        clearTimeout(timer);
        timer = setTimeout(applySearch, 150);
    });
})();
```

- [ ] **Step 4: Verify template syntax**

```bash
cd /Users/k1n4_l0v3d/Desktop/expence_tracker-main && source venv/bin/activate
python -c "
from app import app
with app.app_context():
    from jinja2 import Environment
    import os
    env = app.jinja_env
    src = open('templates/expenses/list.html').read()
    env.parse(src)
    print('Template syntax OK')
"
```

Expected: `Template syntax OK`

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add templates/expenses/list.html
git commit -m "feat: add client-side expense search with debounce and total recalculation"
```

---

## Task 7: Final integration check

- [ ] **Step 1: Start the dev server**

```bash
cd /Users/k1n4_l0v3d/Desktop/expence_tracker-main && source venv/bin/activate
flask run --port 5000
```

- [ ] **Step 2: Manual smoke test checklist**

Open http://localhost:5000 and verify:

1. Dashboard loads with no errors
2. Set a budget limit for a category, add expenses to reach 80%+ → ⚠️ icon appears in category row with yellow background, toast appears once on page load
3. Exceed budget → 🔴 icon, red background row
4. Go to Profile → "Уведомления" card with threshold input visible, change to 90, save → flash "Настройки сохранены"
5. Go to `/expenses` → search input visible in filter row
6. Type a description that matches some expenses → matching cards visible, others hidden, counter shows "N из M", total updates
7. Clear search → all cards reappear, total restores

- [ ] **Step 3: Run full test suite one last time**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Final commit if any tweaks were needed**

```bash
git add -p  # stage only intentional changes
git commit -m "fix: integration tweaks for search and budget alerts"
```
