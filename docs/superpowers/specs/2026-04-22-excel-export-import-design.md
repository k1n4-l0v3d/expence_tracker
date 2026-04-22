# Excel Export / Import — Design Spec

**Goal:** Allow users to download all their expenses and incomes for the current year as a single Excel file, and upload that file back to restore or bulk-add records.

**Architecture:** Two new Flask routes (`GET /profile/export`, `POST /profile/import`) + a new UI card in `templates/profile.html`. One new dependency: `openpyxl`. No new models or migrations needed.

---

## Excel File Format

**Filename:** `расходы_доходы_<year>.xlsx` (e.g. `расходы_доходы_2026.xlsx`)

**Sheet 1: «Расходы»**

| Дата | Категория | Сумма | Описание | Плановый | Оплачен | Заметки |
|------|-----------|-------|----------|----------|---------|---------|

- Дата: string `ДД.ММ.ГГГГ`
- Плановый / Оплачен: `Да` or `Нет`
- Описание, Заметки: may be empty
- Sorted by date ascending

**Sheet 2: «Доходы»**

| Дата | Источник | Сумма | Описание | Заметки |
|------|----------|-------|----------|---------|

- Дата: string `ДД.ММ.ГГГГ`
- Источник, Описание, Заметки: plain strings
- Sorted by date ascending

**Formatting:** Header row is bold. Column widths auto-fitted to content.

---

## Backend

### `GET /profile/export`

- Auth: `@login_required`
- Queries `Expense` and `Income` for `current_user.id` where year == `date.today().year`
- Builds workbook in memory (`io.BytesIO`) using `openpyxl` — no disk writes
- Returns `send_file(buf, as_attachment=True, download_name=...)` with MIME `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`

### `POST /profile/import`

- Auth: `@login_required`
- Accepts multipart form field `file` (`.xlsx` only, max 5 MB)
- Reads both sheets with `openpyxl` (data_only=True)
- Skips header row (row 1)

**Per expense row** (required: Дата, Сумма):
1. Parse date from `ДД.ММ.ГГГГ`; skip row if invalid
2. Parse amount as float; skip row if invalid or ≤ 0
3. Category lookup: search by name (case-insensitive) among system categories (`user_id IS NULL`) and user's own categories — first match wins
4. If not found: create new `Category(name=name, user_id=current_user.id)`
5. Parse Плановый / Оплачен: `'да'` (case-insensitive) → `True`, anything else → `False`
6. Create `Expense` record

**Per income row** (required: Дата, Источник, Сумма):
1. Parse date; skip row if invalid
2. Parse amount; skip row if invalid or ≤ 0
3. Source must be non-empty string; skip row if missing
4. Create `Income` record

**After processing all rows:**
- `db.session.commit()` once
- `flash(f'Импортировано: {exp_count} расходов, {inc_count} доходов. Пропущено строк: {skipped}', 'success')`
- `redirect(url_for('profile'))`

**Error cases:**
- No file uploaded → flash danger, redirect
- Not `.xlsx` extension → flash danger, redirect
- File > 5 MB → flash danger, redirect
- Sheet missing → treat as 0 rows for that sheet (don't crash)

---

## UI

New card added to `templates/profile.html` after existing stat cards:

```html
<div class="card">
  <div class="card-body">
    <h6>📊 Данные</h6>

    <!-- Export -->
    <a href="/profile/export" class="btn btn-outline-success btn-sm">
      <i class="bi bi-file-earmark-excel me-1"></i>Скачать Excel за {{ current_year }}
    </a>

    <!-- Import -->
    <form method="POST" action="/profile/import" enctype="multipart/form-data" class="mt-3">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <label class="form-label fw-semibold">Загрузить данные из Excel:</label>
      <div class="d-flex gap-2 align-items-center">
        <input type="file" name="file" accept=".xlsx" class="form-control form-control-sm">
        <button type="submit" class="btn btn-outline-primary btn-sm text-nowrap">
          <i class="bi bi-upload me-1"></i>Загрузить
        </button>
      </div>
    </form>
  </div>
</div>
```

`current_year` passed from the `profile()` view via `date.today().year`.

---

## Dependencies

Add to `requirements.txt`:
```
openpyxl==3.1.2
```

---

## Data Scope

- Export: current calendar year only (`expense_date.year == today.year`)
- Import: no year restriction — rows are inserted with whatever date is in the file
- Attachments: not exported or imported
