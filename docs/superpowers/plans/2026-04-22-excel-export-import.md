# Excel Export / Import — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users download all their expenses and incomes for the current year as one Excel file (two sheets), and upload that file back to restore or bulk-add records.

**Architecture:** Two new Flask routes (`GET /profile/export`, `POST /profile/import`) added to `app.py` after the existing profile routes. A new "Данные" card added to `templates/profile.html`. openpyxl builds and reads `.xlsx` entirely in memory — no disk writes.

**Tech Stack:** Flask 3.1, SQLAlchemy, openpyxl 3.1.2, Bootstrap 5.3, Jinja2, Python `io.BytesIO`.

---

## Files

- Modify: `requirements.txt` — add openpyxl
- Modify: `app.py` — add two routes after line ~521 (after `change_avatar`)
- Modify: `templates/profile.html` — add card in right column after the password card (before `{% endblock %}` at line 132)

---

### Task 1: Add openpyxl dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add openpyxl to requirements.txt**

Open `requirements.txt` and append:

```
openpyxl==3.1.2
```

Final file should look like:
```
Flask==3.1.0
Flask-SQLAlchemy==3.1.1
Flask-Login==0.6.3
Flask-WTF==1.2.2
psycopg2-binary==2.9.9
python-dotenv==1.0.1
gunicorn==23.0.0
pytest==8.3.5
pytest-flask==1.3.0
openpyxl==3.1.2
```

- [ ] **Step 2: Install it**

```bash
pip install openpyxl==3.1.2
```

Expected: `Successfully installed openpyxl-3.1.2` (or "already satisfied").

- [ ] **Step 3: Verify import works**

```bash
python -c "import openpyxl; print(openpyxl.__version__)"
```

Expected: `3.1.2`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "feat: add openpyxl dependency for Excel export/import"
```

---

### Task 2: Backend — export route

**Files:**
- Modify: `app.py` — insert after `change_avatar` function (after line ~521)

- [ ] **Step 1: Add the import at the top of app.py**

`io` is already imported. Add `openpyxl` import after the existing imports block (around line 18):

```python
import openpyxl
from openpyxl.styles import Font
```

- [ ] **Step 2: Add the export route**

Insert after the `change_avatar` function in `app.py`:

```python
@app.route('/profile/export')
@login_required
@ban_check
def profile_export():
    today = date.today()
    year  = today.year

    expenses = (Expense.query
                .filter(Expense.user_id == current_user.id,
                        extract('year', Expense.expense_date) == year)
                .join(Category)
                .order_by(Expense.expense_date)
                .all())

    incomes = (Income.query
               .filter(Income.user_id == current_user.id,
                       extract('year', Income.income_date) == year)
               .order_by(Income.income_date)
               .all())

    wb = openpyxl.Workbook()

    # ── Лист «Расходы» ────────────────────────────────────────────
    ws_exp = wb.active
    ws_exp.title = 'Расходы'
    exp_headers = ['Дата', 'Категория', 'Сумма', 'Описание', 'Плановый', 'Оплачен', 'Заметки']
    ws_exp.append(exp_headers)
    for cell in ws_exp[1]:
        cell.font = Font(bold=True)

    for exp in expenses:
        ws_exp.append([
            exp.expense_date.strftime('%d.%m.%Y'),
            exp.category.name,
            float(exp.amount),
            exp.description or '',
            'Да' if exp.is_planned else 'Нет',
            'Да' if exp.is_spent  else 'Нет',
            exp.notes or '',
        ])

    for col in ws_exp.columns:
        width = max(len(str(cell.value or '')) for cell in col) + 4
        ws_exp.column_dimensions[col[0].column_letter].width = min(width, 40)

    # ── Лист «Доходы» ────────────────────────────────────────────
    ws_inc = wb.create_sheet('Доходы')
    inc_headers = ['Дата', 'Источник', 'Сумма', 'Описание', 'Заметки']
    ws_inc.append(inc_headers)
    for cell in ws_inc[1]:
        cell.font = Font(bold=True)

    for inc in incomes:
        ws_inc.append([
            inc.income_date.strftime('%d.%m.%Y'),
            inc.source,
            float(inc.amount),
            inc.description or '',
            inc.notes or '',
        ])

    for col in ws_inc.columns:
        width = max(len(str(cell.value or '')) for cell in col) + 4
        ws_inc.column_dimensions[col[0].column_letter].width = min(width, 40)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f'расходы_доходы_{year}.xlsx'
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
```

- [ ] **Step 3: Manually verify export works**

Run `python app.py`, open `http://localhost:5000/profile`, and check that the export link (which we'll add in Task 4) triggers a file download. For now, test directly:

```
http://localhost:5000/profile/export
```

Expected: browser downloads `расходы_доходы_2026.xlsx`. Open it — two sheets, headers bold, data present.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: add GET /profile/export route for Excel download"
```

---

### Task 3: Backend — import route

**Files:**
- Modify: `app.py` — insert after `profile_export` function

- [ ] **Step 1: Add the import route**

Insert directly after the `profile_export` function:

```python
@app.route('/profile/import', methods=['POST'])
@login_required
@ban_check
def profile_import():
    f = request.files.get('file')
    if not f or not f.filename:
        flash('Файл не выбран.', 'danger')
        return redirect(url_for('profile'))

    if not f.filename.lower().endswith('.xlsx'):
        flash('Допускается только формат .xlsx.', 'danger')
        return redirect(url_for('profile'))

    data = f.read()
    if len(data) > 5 * 1024 * 1024:
        flash('Файл слишком большой (максимум 5 МБ).', 'danger')
        return redirect(url_for('profile'))

    try:
        wb = openpyxl.load_workbook(filename=io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        flash('Не удалось прочитать файл. Убедитесь, что это корректный .xlsx.', 'danger')
        return redirect(url_for('profile'))

    exp_count = inc_count = skipped = 0

    # ── Импорт расходов ───────────────────────────────────────────
    if 'Расходы' in wb.sheetnames:
        ws = wb['Расходы']
        rows = iter(ws.rows)
        next(rows, None)  # пропустить заголовок
        for row in rows:
            vals = [cell.value for cell in row]
            if len(vals) < 3:
                skipped += 1
                continue
            date_str, cat_name, amount_val = vals[0], vals[1], vals[2]
            desc      = str(vals[3]).strip() if len(vals) > 3 and vals[3] else ''
            planned   = str(vals[4]).strip().lower() == 'да' if len(vals) > 4 and vals[4] else False
            spent     = str(vals[5]).strip().lower() == 'да' if len(vals) > 5 and vals[5] else True
            notes     = str(vals[6]).strip() if len(vals) > 6 and vals[6] else ''

            # Дата
            try:
                if isinstance(date_str, date):
                    exp_date = date_str
                else:
                    from datetime import datetime as dt
                    exp_date = dt.strptime(str(date_str).strip(), '%d.%m.%Y').date()
            except (ValueError, TypeError):
                skipped += 1
                continue

            # Сумма
            try:
                amount = float(amount_val)
                if amount <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                skipped += 1
                continue

            # Категория
            cat_name_str = str(cat_name).strip() if cat_name else ''
            if not cat_name_str:
                cat_name_str = 'Прочее'

            category = Category.query.filter(
                db.func.lower(Category.name) == cat_name_str.lower(),
                db.or_(Category.user_id.is_(None), Category.user_id == current_user.id),
                Category.is_active.is_(True),
            ).first()

            if not category:
                category = Category(name=cat_name_str, user_id=current_user.id)
                db.session.add(category)
                db.session.flush()  # получить id

            db.session.add(Expense(
                user_id      = current_user.id,
                category_id  = category.id,
                amount       = amount,
                description  = desc or None,
                expense_date = exp_date,
                is_planned   = planned,
                is_spent     = spent,
                notes        = notes or None,
            ))
            exp_count += 1

    # ── Импорт доходов ────────────────────────────────────────────
    if 'Доходы' in wb.sheetnames:
        ws = wb['Доходы']
        rows = iter(ws.rows)
        next(rows, None)  # пропустить заголовок
        for row in rows:
            vals = [cell.value for cell in row]
            if len(vals) < 3:
                skipped += 1
                continue
            date_str, source_val, amount_val = vals[0], vals[1], vals[2]
            desc  = str(vals[3]).strip() if len(vals) > 3 and vals[3] else ''
            notes = str(vals[4]).strip() if len(vals) > 4 and vals[4] else ''

            # Дата
            try:
                if isinstance(date_str, date):
                    inc_date = date_str
                else:
                    from datetime import datetime as dt
                    inc_date = dt.strptime(str(date_str).strip(), '%d.%m.%Y').date()
            except (ValueError, TypeError):
                skipped += 1
                continue

            # Сумма
            try:
                amount = float(amount_val)
                if amount <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                skipped += 1
                continue

            # Источник
            source = str(source_val).strip() if source_val else ''
            if not source:
                skipped += 1
                continue

            db.session.add(Income(
                user_id     = current_user.id,
                amount      = amount,
                source      = source,
                description = desc or None,
                income_date = inc_date,
                notes       = notes or None,
            ))
            inc_count += 1

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Ошибка при сохранении данных.', 'danger')
        return redirect(url_for('profile'))

    word_exp = 'расход' if exp_count == 1 else ('расхода' if exp_count < 5 else 'расходов')
    word_inc = 'доход'  if inc_count == 1 else ('дохода'  if inc_count < 5 else 'доходов')
    msg = f'Импортировано: {exp_count} {word_exp}, {inc_count} {word_inc}.'
    if skipped:
        msg += f' Пропущено строк: {skipped}.'
    flash(msg, 'success')
    return redirect(url_for('profile'))
```

- [ ] **Step 2: Manually verify import**

1. First export your data: `http://localhost:5000/profile/export`
2. Open the downloaded `.xlsx`, add a new row in «Расходы» with a new category name (e.g. «Тест»)
3. Go to `http://localhost:5000/profile`, upload the modified file
4. Expected flash: «Импортировано: N расходов, M доходов.»
5. Check `/expenses` — new rows appear, new category «Тест» created

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add POST /profile/import route for Excel upload"
```

---

### Task 4: UI — «Данные» card in profile.html

**Files:**
- Modify: `templates/profile.html` — insert before `{% endblock %}` at line 132 (end of right column)

- [ ] **Step 1: Add the data card**

In `templates/profile.html`, find the closing tags of the right column (just before `{% endblock %}`):

```html
    </div>
</div>
{% endblock %}
```

Insert the new card between the password card's closing `</div>` and the column's closing `</div>`:

```html
        <!-- Экспорт / Импорт данных -->
        <div class="card shadow-sm border-0 mt-4">
            <div class="card-header border-0 fw-semibold pt-3">
                <i class="bi bi-file-earmark-excel me-2 text-success"></i>Данные
            </div>
            <div class="card-body">
                <a href="{{ url_for('profile_export') }}"
                   class="btn btn-outline-success btn-sm">
                    <i class="bi bi-download me-1"></i>Скачать Excel за {{ current_year }}
                </a>

                <hr class="my-3">

                <form method="POST" action="{{ url_for('profile_import') }}"
                      enctype="multipart/form-data">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <label class="form-label fw-semibold">Загрузить данные из Excel:</label>
                    <div class="d-flex gap-2 align-items-center flex-wrap">
                        <input type="file" name="file" accept=".xlsx"
                               class="form-control form-control-sm" style="max-width:260px">
                        <button type="submit" class="btn btn-outline-primary btn-sm text-nowrap">
                            <i class="bi bi-upload me-1"></i>Загрузить
                        </button>
                    </div>
                    <div class="text-muted small mt-1">Только .xlsx, максимум 5 МБ</div>
                </form>
            </div>
        </div>
```

- [ ] **Step 2: Pass `current_year` from the profile view**

In `app.py`, find the `profile()` function (around line 470). Update `render_template` call to include `current_year`:

```python
    return render_template('profile.html',
                           total_expenses=float(total_expenses),
                           total_income=float(total_income),
                           expense_count=expense_count,
                           income_count=income_count,
                           today=today,
                           current_year=today.year)
```

- [ ] **Step 3: Verify UI**

Run app, open `http://localhost:5000/profile`. Verify:
- «Данные» card appears below password card
- «Скачать Excel за 2026» link triggers download
- File input + «Загрузить» button visible
- Upload a valid `.xlsx` → flash message appears with counts

- [ ] **Step 4: Commit**

```bash
git add templates/profile.html app.py
git commit -m "feat: add Excel export/import UI card to profile page"
```
