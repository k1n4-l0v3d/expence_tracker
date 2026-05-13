# Clear All Data — Design Spec

**Goal:** Allow a user to permanently delete all their expenses, incomes, and budget records via a single button in the profile page.

**Architecture:** One new Flask route `POST /profile/clear-data` + a "Опасная зона" UI section in `templates/profile.html` with a Bootstrap modal confirmation. Standard POST form with CSRF token — no JS fetch needed.

---

## Backend

**Route:** `POST /profile/clear-data`

**Auth:** `@login_required`, `@ban_check`

**Logic:**
1. Delete all `Expense` records where `user_id == current_user.id`
2. Delete all `Income` records where `user_id == current_user.id`
3. Delete all `MonthlyBudget` records where `user_id == current_user.id`
4. `db.session.commit()`
5. `flash('Все данные очищены.', 'warning')`
6. `redirect(url_for('profile'))`

**Not deleted:** `Category` records with `user_id == current_user.id` (custom categories are kept).

**Error handling:** wrap commit in try/except, rollback and flash danger on failure.

---

## UI

### "Опасная зона" card in `templates/profile.html`

Added after the "Данные" card (Excel export/import), still inside the right column:

```html
<div class="card shadow-sm border-0 mt-4 border-danger-subtle">
  <div class="card-header border-0 fw-semibold pt-3 text-danger">
    <i class="bi bi-exclamation-triangle me-2"></i>Опасная зона
  </div>
  <div class="card-body">
    <p class="text-muted small mb-3">
      Расходы, доходы и бюджет за всё время будут удалены безвозвратно.
      Категории сохранятся.
    </p>
    <button type="button" class="btn btn-outline-danger btn-sm"
            data-bs-toggle="modal" data-bs-target="#clearDataModal">
      <i class="bi bi-trash me-1"></i>Очистить все данные
    </button>
  </div>
</div>
```

### Confirmation modal (`#clearDataModal`)

Added to `{% block modals %}` in `templates/profile.html`:

```html
<div class="modal fade" id="clearDataModal" tabindex="-1">
  <div class="modal-dialog modal-dialog-centered">
    <div class="modal-content">
      <div class="modal-header border-0 pb-0">
        <h6 class="modal-title fw-semibold text-danger">
          <i class="bi bi-exclamation-triangle me-2"></i>Удалить все данные?
        </h6>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        Это действие <strong>необратимо</strong>. Все расходы, доходы и бюджет
        будут удалены навсегда. Категории останутся.
      </div>
      <div class="modal-footer border-0 pt-0">
        <button type="button" class="btn btn-outline-secondary btn-sm"
                data-bs-dismiss="modal">Отмена</button>
        <form method="POST" action="/profile/clear-data" class="d-inline">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
          <button type="submit" class="btn btn-danger btn-sm">
            <i class="bi bi-trash me-1"></i>Удалить всё
          </button>
        </form>
      </div>
    </div>
  </div>
</div>
```

---

## Files

- Modify: `app.py` — add route after `profile_import`
- Modify: `templates/profile.html` — add "Опасная зона" card + modal
