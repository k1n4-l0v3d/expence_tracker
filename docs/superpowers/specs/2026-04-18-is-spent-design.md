# Expense «is_spent» — Design Spec

**Date:** 2026-04-18
**Status:** Approved

## Problem

Users can log planned future expenses, but those expenses are immediately counted in totals and balance — even though the money hasn't left their pocket yet. There's no way to distinguish "I plan to spend this" from "I already spent this."

## Solution

Add a boolean `is_spent` field to `Expense`. Only expenses with `is_spent=True` are included in totals, balance, and budget calculations. Unspent expenses are visible in the list with a visual badge and can be confirmed with one tap.

---

## Constraints

- `is_planned` field is unrelated and stays unchanged
- `is_spent` defaults to `True` — normal flow (already spent) requires no extra step
- Unspent expenses still appear in the expense list (not hidden)
- Quick toggle available in list; full toggle available in edit form
- No changes to income model

---

## Data Model

### New column on `Expense`

```python
is_spent = db.Column(db.Boolean, nullable=False, default=True)
```

### Migration (safe pattern already used in project)

```python
exp_columns = [c['name'] for c in inspector.get_columns('expenses')]
if 'is_spent' not in exp_columns:
    with db.engine.connect() as conn:
        conn.execute(text("ALTER TABLE expenses ADD COLUMN is_spent BOOLEAN NOT NULL DEFAULT TRUE;"))
        conn.commit()
```

Existing rows get `is_spent=TRUE` automatically — no data loss, no behaviour change for existing expenses.

---

## Accounting Logic

All summary/total functions filter to `is_spent=True` only:

### `get_monthly_summary()` — lines ~280–285

Add `& Expense.is_spent.is_(True)` to the JOIN condition:

```python
.outerjoin(
    Expense,
    (Expense.category_id == Category.id)
    & (Expense.user_id == user_id)
    & (Expense.is_spent.is_(True))          # NEW
    & (extract('year',  Expense.expense_date) == year)
    & (extract('month', Expense.expense_date) == month),
)
```

This automatically propagates to:
- Dashboard balance (`total_income - total_spent`)
- Budget page category totals
- Stats API (`/api/stats-data`)

---

## Backend Routes

### `POST /expenses/<int:exp_id>/toggle-spent`

```
Auth:    @login_required
Access:  ownership check (exp.user_id == current_user.id)
Action:  flip exp.is_spent
Returns: {"is_spent": bool}  (200)
Errors:  404 if not found or not owner
```

### Updated `expense_add()` and `expense_edit()`

Read `is_spent` from form:
```python
is_spent = request.form.get('is_spent') == 'on'
```

Default in add form: checkbox rendered as `checked`.

---

## Frontend

### Expense List (`templates/expenses/list.html`)

**Badge** — shown when `is_spent=False`:
```html
<span class="badge bg-warning text-dark" style="font-size:.7rem">⏳ Не потрачено</span>
```
Placed next to the category badge row.

**Card background** — `not-spent` class on the card when `is_spent=False`:
```css
.record-card.not-spent {
  background: #fffbf0;
  border: 1.5px dashed #f0c040;
}
```

**Toggle button in action row:**
- `is_spent=False` → green outline button `✓ Потрачено` (calls toggle, updates to spent state)
- `is_spent=True` → small grey icon button `↩` (calls toggle, reverts to unspent)

**AJAX toggle (no page reload):**
```javascript
async function toggleSpent(expId, btn) {
    const res = await fetch(`/expenses/${expId}/toggle-spent`, {
        method: 'POST',
        headers: {'X-CSRFToken': csrfToken},
    });
    const data = await res.json();
    // update badge, button, card class in DOM
}
```

### Expense Form (`templates/expenses/form.html`)

Add checkbox alongside existing `is_planned`:
```html
<div class="form-check">
    <input class="form-check-input" type="checkbox" name="is_spent" id="is_spent"
           {% if not expense or expense.is_spent %}checked{% endif %}>
    <label class="form-check-label" for="is_spent">Деньги уже потрачены</label>
</div>
```

---

## Out of Scope

- Showing a "pending total" summary block on the dashboard
- Filtering expense list by spent/unspent status
- Notifications/reminders for unspent planned expenses
