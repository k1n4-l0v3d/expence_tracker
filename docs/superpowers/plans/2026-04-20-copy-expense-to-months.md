# Copy Expense to Months — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow a user to duplicate a specific expense to one or more months of the current year directly from the expense list.

**Architecture:** One new Flask route `POST /expenses/<exp_id>/copy` + Bootstrap modal in `expenses/list.html` with month checkboxes + copy buttons in the expense card and detail modal.

**Tech Stack:** Flask 3.1, SQLAlchemy, Bootstrap 5.3, vanilla JS (fetch + CSRF from meta tag), Jinja2, Python `calendar` module (already imported).

---

## Files

- Modify: `app.py` — add `POST /expenses/<exp_id>/copy` route after `expense_toggle_spent`
- Modify: `templates/expenses/list.html` — add modal HTML to `{% block modals %}`, copy buttons to card and detail modal, JS logic to `{% block scripts %}`

---

### Task 1: Backend route `POST /expenses/<exp_id>/copy`

**Files:**
- Modify: `app.py` — insert after line ~910 (after `expense_toggle_spent` route)

- [ ] **Step 1: Add the route to `app.py`**

Insert after the `expense_toggle_spent` function:

```python
@app.route('/expenses/<int:exp_id>/copy', methods=['POST'])
@login_required
@ban_check
def expense_copy(exp_id):
    exp = Expense.query.filter_by(id=exp_id, user_id=current_user.id).first_or_404()
    data = request.get_json()
    months = data.get('months') if data else None
    if not months or not isinstance(months, list):
        return jsonify({'error': 'Укажите месяцы'}), 400

    today = date.today()
    current_year = today.year
    created = 0

    for m in months:
        if not isinstance(m, int) or not (1 <= m <= 12):
            continue
        # Clamp day to last day of target month
        max_day = calendar.monthrange(current_year, m)[1]
        target_day = min(exp.expense_date.day, max_day)
        target_date = date(current_year, m, target_day)

        # is_spent: False for future months, original for past/current
        if target_date > today:
            is_spent = False
        else:
            is_spent = exp.is_spent

        copy = Expense(
            user_id      = current_user.id,
            category_id  = exp.category_id,
            amount       = exp.amount,
            description  = exp.description,
            expense_date = target_date,
            is_planned   = exp.is_planned,
            is_spent     = is_spent,
            notes        = exp.notes,
        )
        db.session.add(copy)
        created += 1

    try:
        db.session.commit()
        return jsonify({'created': created})
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Ошибка сохранения'}), 500
```

- [ ] **Step 2: Verify manually**

Run the app: `python app.py`

In browser devtools console, test:
```javascript
fetch('/expenses/1/copy', {
  method: 'POST',
  headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content},
  body: JSON.stringify({months: [1, 3]})
}).then(r => r.json()).then(console.log)
```
Expected: `{created: 2}`

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add expense copy route POST /expenses/<id>/copy"
```

---

### Task 2: Copy modal HTML in `templates/expenses/list.html`

**Files:**
- Modify: `templates/expenses/list.html` — add modal inside `{% block modals %}`

- [ ] **Step 1: Add the copy modal inside `{% block modals %}`**

Add after the closing `</div>` of `#attachmentsModal` (before `{% endblock %}`):

```html
<!-- Модал копирования расхода по месяцам -->
<div class="modal fade" id="copyExpenseModal" tabindex="-1">
    <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
            <div class="modal-header border-0 pb-0">
                <div>
                    <h6 class="modal-title fw-semibold mb-0">
                        <i class="bi bi-copy me-2 text-primary"></i>Копировать расход
                    </h6>
                    <div id="copyExpenseLabel" class="text-muted small mt-1"></div>
                </div>
                <button type="button" class="btn-close ms-auto" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body pt-2">
                <div class="form-check mb-2">
                    <input class="form-check-input" type="checkbox" id="copySelectAll">
                    <label class="form-check-label fw-semibold" for="copySelectAll">Выбрать все месяцы</label>
                </div>
                <hr class="my-2">
                <div class="row g-2" id="copyMonthsGrid">
                    <!-- заполняется JS -->
                </div>
            </div>
            <div class="modal-footer border-0 pt-0">
                <button type="button" class="btn btn-outline-secondary btn-sm" data-bs-dismiss="modal">Отмена</button>
                <button type="button" class="btn grad-primary btn-sm" id="copyExpenseSubmit" disabled
                        onclick="submitCopyExpense()">
                    <i class="bi bi-copy me-1"></i>Копировать
                </button>
            </div>
        </div>
    </div>
</div>
```

- [ ] **Step 2: Verify HTML renders without errors**

Open `http://localhost:5000/expenses` — no console errors, page loads normally.

- [ ] **Step 3: Commit**

```bash
git add templates/expenses/list.html
git commit -m "feat: add copy expense modal HTML"
```

---

### Task 3: Copy button in expense card and detail modal

**Files:**
- Modify: `templates/expenses/list.html` — add button in card action row and in detail modal

- [ ] **Step 1: Add copy button in the expense card**

In the card action buttons (inside the `{% if exp.attachments %}` block area, find the edit button `<a href="{{ url_for('expense_edit'...`), insert BEFORE it:

```html
<button type="button" class="btn btn-sm btn-outline-primary"
        style="min-height:34px;padding:4px 8px"
        aria-label="Копировать на другие месяцы"
        onclick="openCopyModal({{ exp.id }}, {{ exp.expense_date.month }}, {{ (exp.description or exp.category.name) | tojson }}, '{{ '%.2f'|format(exp.amount|float) }}')">
    <i class="bi bi-copy" aria-hidden="true"></i>
</button>
```

- [ ] **Step 2: Add copy button in the expense detail modal footer**

The `#expenseDetailModal` currently has no footer. Add one inside `.modal-content`, after `.modal-body`:

```html
            <div class="modal-footer border-0 pt-0 justify-content-start">
                <button type="button" class="btn btn-outline-primary btn-sm"
                        id="copyFromDetailBtn" onclick="">
                    <i class="bi bi-copy me-1"></i>Скопировать на другие месяцы
                </button>
            </div>
```

The `onclick` will be wired in Task 4 JS (the button stores data via a global variable set when `openExpenseDetail` is called).

- [ ] **Step 3: Add `data-exp-id` to the clickable info div in the card**

In the card's info div (the one with `onclick="openExpenseDetail(this)"`), add `data-exp-id="{{ exp.id }}"`:

```html
<div style="min-width:0;cursor:pointer;flex:1"
     role="button"
     tabindex="0"
     data-exp-id="{{ exp.id }}"
     onclick="openExpenseDetail(this)"
     ...>
```

- [ ] **Step 4: Wire the detail modal button via `openExpenseDetail`**

In the existing `openExpenseDetail(el)` function, add at the end before the modal show lines:

```javascript
    // Сохранить данные для кнопки копирования
    const copyBtn = document.getElementById('copyFromDetailBtn');
    if (copyBtn) {
        const expId = el.dataset.expId;
        const expMonth = new Date(expData.date.split('.').reverse().join('-')).getMonth() + 1;
        copyBtn.onclick = () => {
            bootstrap.Modal.getInstance(document.getElementById('expenseDetailModal'))?.hide();
            openCopyModal(expId, expMonth, expData.description || expData.category, expData.amount);
        };
    }
```

Note: `expData` is already parsed at the top of `openExpenseDetail` as `const exp = JSON.parse(el.dataset.exp)` — rename reference to match: use `exp.date`, `exp.description`, `exp.category`, `exp.amount`.

- [ ] **Step 4: Verify buttons appear**

Open expenses list — each card should have a copy icon button. Click a card — detail modal should show «Скопировать на другие месяцы» button in footer.

- [ ] **Step 5: Commit**

```bash
git add templates/expenses/list.html
git commit -m "feat: add copy buttons to expense card and detail modal"
```

---

### Task 4: JavaScript logic for copy modal

**Files:**
- Modify: `templates/expenses/list.html` — add JS to `{% block scripts %}`

- [ ] **Step 1: Add JS variables and `openCopyModal` function**

Add to the `<script>` block (after existing globals like `_attachmentsGrid`):

```javascript
const MONTH_NAMES = ['Январь','Февраль','Март','Апрель','Май','Июнь',
                     'Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'];
let _copyExpId = null;
let _copyExpMonth = null;

function openCopyModal(expId, expMonth, label, amount) {
    _copyExpId = expId;
    _copyExpMonth = parseInt(expMonth);

    document.getElementById('copyExpenseLabel').textContent = label + ' — ' + amount + ' ₽';

    // Построить чекбоксы месяцев
    const grid = document.getElementById('copyMonthsGrid');
    grid.innerHTML = '';
    for (let m = 1; m <= 12; m++) {
        const disabled = (m === _copyExpMonth);
        const col = document.createElement('div');
        col.className = 'col-6';
        col.innerHTML = `<div class="form-check">
            <input class="form-check-input copy-month-cb" type="checkbox"
                   id="copyMonth${m}" value="${m}" ${disabled ? 'disabled' : ''}
                   onchange="updateCopySubmitBtn()">
            <label class="form-check-label ${disabled ? 'text-muted' : ''}" for="copyMonth${m}">
                ${MONTH_NAMES[m-1]}${disabled ? ' <span class="text-muted small">(текущий)</span>' : ''}
            </label>
        </div>`;
        grid.appendChild(col);
    }

    // Сбросить «выбрать все»
    document.getElementById('copySelectAll').checked = false;
    updateCopySubmitBtn();

    const modalEl = document.getElementById('copyExpenseModal');
    if (modalEl.parentElement !== document.body) document.body.appendChild(modalEl);
    bootstrap.Modal.getOrCreateInstance(modalEl).show();
}

function updateCopySubmitBtn() {
    const any = [...document.querySelectorAll('.copy-month-cb:not(:disabled)')]
        .some(cb => cb.checked);
    document.getElementById('copyExpenseSubmit').disabled = !any;

    // Синхронизировать «выбрать все»
    const allChecked = [...document.querySelectorAll('.copy-month-cb:not(:disabled)')]
        .every(cb => cb.checked);
    document.getElementById('copySelectAll').checked = allChecked;
}

document.addEventListener('change', function(e) {
    if (e.target.id === 'copySelectAll') {
        document.querySelectorAll('.copy-month-cb:not(:disabled)')
            .forEach(cb => { cb.checked = e.target.checked; });
        updateCopySubmitBtn();
    }
});

async function submitCopyExpense() {
    const months = [...document.querySelectorAll('.copy-month-cb:checked')]
        .map(cb => parseInt(cb.value));
    if (!months.length) return;

    const btn = document.getElementById('copyExpenseSubmit');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Копирование...';

    try {
        const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
        const res = await fetch(`/expenses/${_copyExpId}/copy`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
            body: JSON.stringify({months}),
        });
        const data = await res.json();
        if (!res.ok) { alert(data.error || 'Ошибка'); return; }

        bootstrap.Modal.getInstance(document.getElementById('copyExpenseModal')).hide();

        // Показать сообщение об успехе
        const word = data.created === 1 ? 'месяц' : data.created < 5 ? 'месяца' : 'месяцев';
        const alertEl = document.createElement('div');
        alertEl.className = 'alert alert-success alert-dismissible fade show stagger-item';
        alertEl.innerHTML = `<i class="bi bi-check-circle me-1"></i>Скопировано в ${data.created} ${word}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
        document.querySelector('.page-wrapper, .container')?.prepend(alertEl);
        setTimeout(() => alertEl?.remove(), 4000);
    } catch(e) {
        alert('Ошибка: ' + e.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-copy me-1"></i>Копировать';
    }
}
```

- [ ] **Step 2: Verify full flow**

1. Open `/expenses`
2. Click copy icon on any expense card → modal opens with 12 month checkboxes, current month disabled
3. «Выбрать все» selects all enabled checkboxes; «Копировать» button becomes active
4. Select 2–3 months, click «Копировать» → spinner → modal closes → success alert appears
5. Navigate to one of the copied months → expense appears there
6. Click a card → open detail modal → click «Скопировать на другие месяцы» → same copy modal opens

- [ ] **Step 3: Commit**

```bash
git add templates/expenses/list.html
git commit -m "feat: complete copy expense to months UI and JS"
```
