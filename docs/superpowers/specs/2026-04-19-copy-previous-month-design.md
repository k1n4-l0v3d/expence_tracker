# Copy From Previous Month — Design Spec

**Date:** 2026-04-19
**Status:** Approved

## Problem

Users with recurring planned expenses and regular income sources must re-enter the same data every month manually. There is no way to carry forward last month's template to a new empty month.

## Solution

A "copy from previous month" button appears on the dashboard next to the month/year filter, but **only** when the selected month is empty and the previous month has data. One click copies all planned expenses and all income from the previous month into the selected month.

---

## Constraints

- Button visible only when: selected month has 0 expenses AND 0 income, AND previous month has ≥1 planned expense (`is_planned=True`) or ≥1 income
- Only planned expenses (`is_planned=True`) are copied — unplanned expenses are skipped
- All income entries are copied regardless of type
- Attachments are NOT copied
- Copied expenses get `is_spent=False` (not yet spent in new month)
- Date logic: same day-of-month; if target month is shorter, cap to last day of target month
- Simple POST + redirect — no AJAX, no confirmation modal
- Flash message shown after copy

---

## Backend

### `can_copy` flag in `index()` route (`app.py`)

After computing `total_spent` and `total_income`, calculate the previous month and check both months:

```python
# Previous month
prev_month = month - 1 if month > 1 else 12
prev_year  = year if month > 1 else year - 1

# Current month is empty
current_empty = (total_spent == 0 and total_income == 0)

# Previous month has data to copy
prev_has_expenses = Expense.query.filter_by(
    user_id=uid, is_planned=True
).filter(
    extract('year',  Expense.expense_date) == prev_year,
    extract('month', Expense.expense_date) == prev_month,
).count() > 0

prev_has_income = Income.query.filter(
    Income.user_id == uid,
    extract('year',  Income.income_date) == prev_year,
    extract('month', Income.income_date) == prev_month,
).count() > 0

can_copy = current_empty and (prev_has_expenses or prev_has_income)
```

Pass `can_copy`, `year`, `month` to template (already passed).

### `POST /copy-from-previous` route

```
Auth:    @login_required, @ban_check
Params:  year (int), month (int) — target month (from form hidden fields)
Action:
  1. Compute prev_month / prev_year
  2. Load planned expenses from prev month
  3. Load all income from prev month
  4. For each expense: create new Expense with same fields, date adjusted
  5. For each income: create new Income with same fields, date adjusted
  6. db.session.commit()
  7. flash("Скопировано {n_exp} расходов и {n_inc} доходов из {prev_month_name}.", "success")
  8. redirect to /?year=Y&month=M
```

### Date adjustment helper

```python
def adjust_day(day: int, year: int, month: int) -> int:
    """Cap day to last day of target month."""
    import calendar
    return min(day, calendar.monthrange(year, month)[1])
```

### Month name helper

Use existing `months_list()` to get Russian month name for flash message:
```python
month_names = {m: name for m, name in months_list()}
prev_month_name = month_names[prev_month]
```

---

## Frontend (`templates/index.html`)

### Button placement

Inside the existing filter `<form>`, after the submit button (line ~20):

```html
{% if can_copy %}
<form method="post" action="{{ url_for('copy_from_previous') }}" class="d-inline">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <input type="hidden" name="year"  value="{{ year }}">
    <input type="hidden" name="month" value="{{ month }}">
    <button type="submit" class="btn btn-outline-primary btn-sm" title="Скопировать из предыдущего месяца">
        <i class="bi bi-copy me-1"></i>Скопировать
    </button>
</form>
{% endif %}
```

---

## Data Flow

1. User navigates to `/?year=2026&month=5` (empty month)
2. `index()` detects: current month empty, April has planned expenses/income → `can_copy=True`
3. Template renders the «Скопировать» button next to the month filter
4. User clicks → `POST /copy-from-previous` with `year=2026&month=5`
5. Route copies April's planned expenses and all income into May (dates adjusted)
6. Flash: «Скопировано 4 расходов и 2 доходов из April.»
7. Redirect to `/?year=2026&month=5` — dashboard shows copied data, button gone

---

## Out of Scope

- Undo / rollback after copying
- Selective copy (choose which items to copy)
- Copy budget limits (MonthlyBudget)
- Copying between arbitrary months (only previous → current selected)
