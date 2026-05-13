# Expense Attachments — Design Spec

**Date:** 2026-04-18
**Status:** Approved

## Problem

Users cannot attach receipts or photos to expenses. There is no way to store documentary evidence of a purchase within the app.

## Solution

Allow users to attach multiple image files (JPG, PNG, WEBP) and PDFs to any expense. Files are stored as binary blobs in the PostgreSQL database — no external storage service required. Works on Railway and locally.

---

## Constraints

- **File types:** `image/jpeg`, `image/png`, `image/webp`, `application/pdf`
- **Max size per file:** 10 MB
- **Max files per expense:** 10
- **Storage:** PostgreSQL `LargeBinary` (BYTEA) column — no filesystem, no cloud

---

## Data Model

New table `expense_attachments`:

```python
class ExpenseAttachment(db.Model):
    __tablename__ = 'expense_attachments'

    id         = db.Column(db.Integer, primary_key=True)
    expense_id = db.Column(db.Integer, db.ForeignKey('expenses.id', ondelete='CASCADE'), nullable=False)
    filename   = db.Column(db.String(255), nullable=False)
    mime_type  = db.Column(db.String(100), nullable=False)
    data       = db.Column(db.LargeBinary, nullable=False)
    size       = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
```

Relationship on `Expense`:
```python
attachments = db.relationship('ExpenseAttachment', backref='expense',
                              lazy=True, cascade='all, delete-orphan')
```

Migration: `db.create_all()` handles it (new table, no ALTER TABLE needed).

---

## Backend Routes

### `GET /attachments/<id>`
- Auth: `@login_required`, ownership check (`attachment.expense.user_id == current_user.id`)
- Returns file via `send_file()` with correct `mimetype` and `Content-Disposition`
- For images: `inline`; for PDFs: `inline` (browser renders) with download fallback

### `POST /expenses/<expense_id>/attachments`
- Auth: `@login_required`, ownership check on expense
- Accepts multipart `file` field
- Validates: mime type in allowed set, size ≤ 10 MB, attachment count < 10
- Saves `ExpenseAttachment` record, returns `{id, filename, mime_type, size}` JSON (201)
- CSRF: `X-CSRFToken` header

### `DELETE /attachments/<id>`
- Auth: `@login_required`, ownership check
- Deletes record, returns `{ok: true}` JSON (200)
- CSRF: `X-CSRFToken` header

---

## Frontend

### Expense Form (`templates/expenses/form.html`)

Add an **Attachments section** below the Notes field:

- Shows existing attachments as 60×60px thumbnail grid (images show preview via `/attachments/<id>`, PDFs show 📄 icon)
- Each thumbnail has a red ✕ button — AJAX DELETE, removes from DOM on success
- "Добавить фото или PDF" dashed-border label with `<input type="file" multiple accept="image/*,.pdf">`
- On file select: JS uploads each file via `fetch POST /expenses/<id>/attachments`, shows thumbnail immediately on success, shows error inline on failure
- **On new expense (add form):** files are queued client-side, uploaded after the expense is created (two-step: create expense → upload files)
- **On existing expense (edit form):** uploads happen immediately

### Expense List (`templates/expenses/list.html`)

- Pass attachment counts with expenses (via eager loading or annotation)
- If expense has attachments: show `📎N` badge next to amount (blue, clickable)
- Click opens Bootstrap modal `#attachmentsModal` (shared, loaded once per page)
- Modal title: `"{description}" · N файлов`
- Modal body: images shown as `<img src="/attachments/<id>">` thumbnails (click to open full-size in new tab), PDFs shown as icon + filename + "↓ Скачать" link
- Modal populated via JS from inline JSON data attribute on the badge element

---

## Error Handling

| Scenario | Response |
|----------|----------|
| Wrong MIME type | 415 + `{error: "Недопустимый тип файла"}` |
| File > 10 MB | 413 + `{error: "Файл слишком большой (макс. 10 МБ)"}` |
| > 10 files on expense | 409 + `{error: "Максимум 10 вложений на расход"}` |
| Unauthorized access | 403 |
| DB error on save | 500 + `{error: "Ошибка сохранения"}` |

---

## Performance Note

Storing large blobs in PostgreSQL increases DB size. For a personal expense tracker with ≤10 files per expense at ≤10 MB each, this is acceptable. Images should be served with appropriate cache headers (`Cache-Control: private, max-age=3600`).

---

## Out of Scope

- Image compression/resizing
- Attachment editing (rename)
- Bulk download
- Attachment search
