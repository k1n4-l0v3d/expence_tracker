# Search & Budget Alerts — Design Spec

**Date:** 2026-05-07
**Status:** Approved

---

## Feature 1: Client-side Expense Search

### Problem

The expense list grows over time and there is no way to find a specific entry by description, notes, or category name without scrolling manually.

### Solution

Add a text input to the existing filter row on `/expenses`. JS filters visible cards instantly on each keystroke — no server round-trip.

---

### Frontend (`templates/expenses/list.html`)

#### Search input

Added to the existing `filter-form` div after the category select (around line 28):

```html
<div class="input-group input-group-sm" style="width:200px">
  <span class="input-group-text"><i class="bi bi-search"></i></span>
  <input type="text" id="expenseSearch" class="form-control"
         placeholder="Поиск..." autocomplete="off">
  <span id="searchCount" class="input-group-text d-none"
        style="font-size:.75rem;white-space:nowrap"></span>
</div>
```

- Not submitted to the server (`name` attribute absent)
- Counter badge (`N из M`) shown when query is non-empty, hidden otherwise

#### JS logic (added to existing `<script>` block)

```javascript
(function () {
    const input  = document.getElementById('expenseSearch');
    const cards  = () => document.querySelectorAll('.record-card');
    const countEl = document.getElementById('searchCount');
    let timer;

    function applySearch() {
        const q = input.value.trim().toLowerCase();
        let visible = 0, total = 0;
        cards().forEach(card => {
            total++;
            if (!q) { card.style.display = ''; visible++; return; }
            const desc     = (card.querySelector('.fw-semibold')?.textContent || '').toLowerCase();
            const notes    = (card.querySelector('.fst-italic')?.textContent  || '').toLowerCase();
            const category = (card.querySelector('.badge')?.textContent       || '').toLowerCase();
            const match    = desc.includes(q) || notes.includes(q) || category.includes(q);
            card.style.display = match ? '' : 'none';
            if (match) visible++;
        });
        // Counter
        if (q) {
            countEl.textContent = `${visible} из ${total}`;
            countEl.classList.remove('d-none');
        } else {
            countEl.classList.add('d-none');
        }
        // Recalculate total row
        const totalEl = document.querySelector('.filter-total-amount');
        if (totalEl) {
            let sum = 0;
            cards().forEach(card => {
                if (card.style.display !== 'none') {
                    const amt = parseFloat(card.querySelector('.fw-bold.fs-6')?.textContent) || 0;
                    sum += amt;
                }
            });
            totalEl.textContent = sum.toFixed(2) + ' ₽';
        }
    }

    input.addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(applySearch, 150);
    });
})();
```

**Searched fields (per card):**
- `.fw-semibold` — description
- `.fst-italic` — notes
- `.badge` (first badge) — category name

**Total row:** the existing итого row updates to sum only visible cards. The `итого` span needs `class="filter-total-amount"` added.

---

## Feature 2: Budget Alerts

### Problem

Users set per-category budget limits but receive no feedback when approaching or exceeding them, except for a static progress bar.

### Solution

Two-layer alert:
1. Inline icon/highlight in the category list on the dashboard (persistent)
2. Toast notification on dashboard load (once per browser session)

Threshold is configurable per user (default 80%).

---

### Backend (`app.py`)

#### Model change — `User`

Add one column:

```python
budget_alert_pct = db.Column(db.Integer, default=80, nullable=False)
```

Range: 1–100. Default 80 means "warn when ≥ 80% of budget is spent".

#### `index()` route — build `alert_map`

After `summary` and `budget_map` are computed:

```python
alert_pct = current_user.budget_alert_pct
alert_map = {}  # cat_id -> 'warning' | 'exceeded'
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

Pass `alert_map` to `render_template`.

#### Context processor — `inject_budget_alerts`

New context processor (next to `inject_reminders`):

```python
@app.context_processor
def inject_budget_alerts():
    if not current_user.is_authenticated:
        return {'budget_alerts': []}
    year  = date.today().year
    month = date.today().month
    summary   = get_monthly_summary(current_user.id, year, month)
    bmap      = get_budget_map(current_user.id, year, month)
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

- Only checks **current real month** (not the month filter on the dashboard)
- Uses existing `get_monthly_summary` and `get_budget_map` helpers

#### New route — save threshold

New `POST /profile/budget-alert-pct` route (analogous to `/profile/change-password`):

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

---

### Frontend — Dashboard (`templates/index.html`)

#### Category list row (around line 214)

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

Row background highlight added via inline style on `<li>`:

```html
<li class="list-group-item px-3 py-3
    {% if alert_map.get(row.id) == 'warning' %}alert-warning-row
    {% elif alert_map.get(row.id) == 'exceeded' %}alert-exceeded-row{% endif %}">
```

CSS in `static/css/style.css`:

```css
.alert-warning-row  { background: rgba(255, 193, 7, 0.08) !important; }
.alert-exceeded-row { background: rgba(220, 53, 69, 0.08) !important; }
[data-bs-theme="dark"] .alert-warning-row  { background: rgba(255, 193, 7, 0.10) !important; }
[data-bs-theme="dark"] .alert-exceeded-row { background: rgba(220, 53, 69, 0.10) !important; }
```

---

### Frontend — Toast (`templates/base.html`)

Added in the existing toast container (next to reminders):

```html
{% if budget_alerts %}
<div class="toast" id="budget-alert-toast" role="alert" data-bs-autohide="true" data-bs-delay="8000">
  <div class="toast-header">
    <strong class="me-auto">💰 Бюджет</strong>
    <button type="button" class="btn-close" data-bs-dismiss="toast"></button>
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
{% endif %}
```

JS (next to reminders JS):

```javascript
const budgetToast = document.getElementById('budget-alert-toast');
if (budgetToast && !sessionStorage.getItem('budget_toast_shown')) {
    sessionStorage.setItem('budget_toast_shown', '1');
    new bootstrap.Toast(budgetToast).show();
}
```

- One combined toast for all alerts (not one per category)
- Shown once per browser session via `sessionStorage`

---

### Frontend — Profile (`templates/profile.html`)

New input in settings section:

```html
<form method="post" action="{{ url_for('profile_budget_alert_pct') }}">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  <div class="mb-3">
    <label class="form-label fw-semibold">Порог бюджетного алерта (%)</label>
    <input type="number" name="budget_alert_pct" class="form-control"
           min="1" max="100" value="{{ current_user.budget_alert_pct }}">
    <div class="form-text">Уведомление появится когда расходы категории достигнут этого % от лимита</div>
  </div>
  <button type="submit" class="btn grad-primary btn-sm">Сохранить</button>
</form>
```

---

## Database Migration

New column on `users` table:

```sql
ALTER TABLE users ADD COLUMN budget_alert_pct INTEGER NOT NULL DEFAULT 80;
```

Executed via `db.create_all()` if using SQLite dev setup, or applied manually on production.

---

## Out of Scope

- Per-category alert thresholds
- Push / email notifications for budget alerts
- Search across multiple months (search is client-side, current month only)
- Fuzzy / typo-tolerant search
- Highlighting matched text in search results
