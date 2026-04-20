# Copy Expense to Months — Design Spec

**Goal:** Allow a user to duplicate a specific expense card to one or more months of the current year.

**Architecture:** Single new API route + Bootstrap modal with month checkboxes. No new models or migrations needed. Pure JS/Jinja2 on the frontend, one Flask route on the backend.

---

## UI Entry Points

The copy button (`bi-copy` icon) appears in two places:

1. **Expense card** — in the action buttons row, between the paperclip/spent buttons and the pencil button
2. **Expense detail modal** — a "Скопировать на другие месяцы" button in the modal footer

Clicking either stores the expense ID and opens `#copyExpenseModal`.

## Copy Modal (`#copyExpenseModal`)

- **Header:** «Копировать расход» + subtitle showing category name + amount
- **Body:**
  - Checkbox «Выбрать все месяцы» with a divider
  - 12 checkboxes: Январь–Декабрь of the current year
  - The month of the original expense is disabled and unchecked
- **Footer:**
  - «Копировать» button — disabled when no month is selected; shows spinner on submit
  - «Отмена» button
- **On success:** modal closes, flash-style alert «Скопировано в N месяц(ев)» shown inline

## Backend

**Route:** `POST /expenses/<exp_id>/copy`

**Auth:** `@login_required`, `@ban_check`. Validates `exp.user_id == current_user.id` (403 otherwise).

**Request body (JSON):**
```json
{"months": [1, 3, 5]}
```
Months are 1-indexed integers. Year is always the current year (server-side).

**Logic per target month:**
- Copy fields: `category_id`, `amount`, `description`, `is_planned`, `notes`
- Date: same day-of-month as original; if target month is shorter, use last day of that month
- `is_spent`: `False` for months after today's month, original value for months before or equal to today's month
- Attachments: not copied

**Response:**
```json
{"created": 3}
```

**Errors:** 400 if `months` missing/empty, 403 if not owner, 404 if expense not found.

## Data Flow

1. User clicks copy button → JS stores `expId`, `expMonth` (to disable in modal), `expLabel` (category + amount for subtitle)
2. Modal opens with correct month disabled
3. «Выбрать все» toggles all enabled checkboxes
4. «Копировать» button activates when ≥1 month selected
5. Submit → `POST /expenses/<expId>/copy` with selected months
6. Success → close modal, show inline success message
