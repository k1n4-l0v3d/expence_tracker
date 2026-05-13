# In-App Expense Reminders — Design Spec

**Date:** 2026-04-19
**Status:** Approved

## Problem

Users log planned expenses with `is_spent=False` but have no way to know when those expenses are due. They may forget to confirm a payment on the day it's scheduled.

## Solution

Show a Bootstrap Toast notification per unspent expense due tomorrow, automatically injected into every page via a Flask context processor. Shown once per browser session using `sessionStorage`.

---

## Constraints

- In-app only (no browser push, no email)
- One toast per expense (not a combined banner)
- Shown once per session — closing a toast prevents it from reappearing until the user logs in again (sessionStorage clears on tab close)
- Only for authenticated users
- No new routes, no background jobs, no new dependencies

---

## Backend

### Context processor

New `@app.context_processor` function `inject_reminders()` added to `app.py`.

```python
@app.context_processor
def inject_reminders():
    if not current_user.is_authenticated:
        return {'reminders': []}
    tomorrow = date.today() + timedelta(days=1)
    reminders = Expense.query.filter_by(
        user_id=current_user.id, is_spent=False
    ).filter(Expense.expense_date == tomorrow).all()
    return {'reminders': reminders}
```

- Runs on every `render_template()` call automatically
- One DB query per page load for authenticated users
- Returns expenses with `is_spent=False` and `expense_date == tomorrow`
- `timedelta` is already imported in `app.py` (used elsewhere); `date` is also already imported

---

## Frontend

### Toast container in `templates/base.html`

Added just before the closing `</body>` tag:

```html
<div class="toast-container position-fixed bottom-0 end-0 p-3" style="z-index:1100">
  {% for exp in reminders %}
  <div class="toast" id="reminder-toast-{{ exp.id }}" role="alert" data-bs-autohide="false">
    <div class="toast-header">
      <strong class="me-auto">⏰ Завтра расход</strong>
      <button type="button" class="btn-close" data-bs-dismiss="toast"></button>
    </div>
    <div class="toast-body">
      {{ exp.description or exp.category.name }} — <strong>{{ "%.0f"|format(exp.amount|float) }} ₽</strong>
    </div>
  </div>
  {% endfor %}
</div>
```

### JS in `templates/base.html`

Added after Bootstrap JS (already loaded in base):

```javascript
document.querySelectorAll('.toast[id^="reminder-toast-"]').forEach(el => {
  const key = 'shown_' + el.id;
  if (!sessionStorage.getItem(key)) {
    sessionStorage.setItem(key, '1');
    new bootstrap.Toast(el).show();
  }
});
```

- Iterates over reminder toasts rendered by Jinja2
- Checks `sessionStorage` — if already shown this session, skips
- Sets key before showing to prevent double-show on fast navigation
- `data-bs-autohide="false"` — toast stays until manually closed

---

## Data Flow

1. User loads any page (authenticated)
2. Context processor queries DB: `Expense` where `user_id=current_user.id`, `is_spent=False`, `expense_date=tomorrow`
3. `reminders` list injected into template context
4. Jinja2 renders one `<div class="toast">` per reminder
5. JS checks each toast's ID against `sessionStorage`
6. New toasts get shown; already-seen ones are skipped
7. IDs stored in `sessionStorage` — cleared automatically when browser tab closes

---

## Out of Scope

- Reminders for expenses due in 2+ days
- Snooze / "remind me later" functionality
- Push notifications (require service worker + VAPID)
- Email reminders
- Admin view of pending reminders
