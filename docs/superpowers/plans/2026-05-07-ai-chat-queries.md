# AI Chat Query Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the AI chat answer analytical questions ("сколько потратил на еду в апреле?", "покажи последние 10 трат") by pre-fetching real DB data before calling Groq.

**Architecture:** New `_extract_query_data(message, user_id, categories)` function detects query intent via keyword scan, runs the appropriate SQL query, and returns a formatted `QUERY DATA:` string. `_build_system_prompt` gains an optional `query_data=""` parameter and appends it to the prompt. `api_chat()` calls `_extract_query_data` before building messages.

**Tech Stack:** Python, SQLAlchemy (existing helpers reused), Flask. No frontend changes.

---

## File Map

| File | Change |
|------|--------|
| `app.py` | Add 5 private helper functions + `_RU_MONTH_NAMES` constant; update `_build_system_prompt` signature; 2 new lines in `api_chat()` |
| `tests/test_chat_queries.py` | New test file — 8 unit tests for `_extract_query_data` |

---

## Task 1: Write failing tests

**Files:**
- Create: `tests/test_chat_queries.py`

- [ ] **Step 1: Create test file**

Create `tests/test_chat_queries.py`:

```python
import pytest
from datetime import date
import calendar
from app import app as flask_app, db, User, Category, Expense, Income, SavingsAccount


def _make_user():
    u = User(username='quser', email='q@example.com')
    u.set_password('pass1234')
    db.session.add(u)
    db.session.flush()
    return u


def _make_cat(user_id, name='Еда'):
    c = Category(name=name, color='#ff0000', icon='bi-bag', user_id=user_id)
    db.session.add(c)
    db.session.flush()
    return c


def _make_expense(user_id, cat_id, amount, expense_date, description=None):
    e = Expense(
        user_id=user_id, category_id=cat_id,
        amount=amount, expense_date=expense_date,
        is_planned=True, is_spent=True,
        description=description,
    )
    db.session.add(e)
    db.session.flush()
    return e


# ── Tests ───────────────────────────────────────────────────────────

def test_category_month_query():
    """Message with category + month returns QUERY DATA with that category's sum."""
    from app import _extract_query_data
    with flask_app.app_context():
        u = _make_user()
        cat = _make_cat(u.id, 'Еда')
        _make_expense(u.id, cat.id, 1500, date(date.today().year, 4, 10))
        _make_expense(u.id, cat.id, 2000, date(date.today().year, 4, 20))
        db.session.commit()

        cats = Category.query.filter_by(user_id=u.id).all()
        result = _extract_query_data('сколько потратил на еду в апреле', u.id, cats)

    assert 'QUERY DATA' in result
    assert 'Еда' in result
    assert '₽' in result
    assert '3500' in result or '3 500' in result


def test_monthly_summary_query():
    """Message with month only returns summary with income/expenses."""
    from app import _extract_query_data
    today = date.today()
    with flask_app.app_context():
        u = _make_user()
        cat = _make_cat(u.id, 'Транспорт')
        _make_expense(u.id, cat.id, 800, date(today.year, 4, 5))
        db.session.commit()

        cats = Category.query.filter_by(user_id=u.id).all()
        result = _extract_query_data('сколько всего потратил в апреле', u.id, cats)

    assert 'QUERY DATA' in result
    assert 'доходы' in result
    assert 'расходы' in result


def test_recent_query_default_10():
    """'покажи последние траты' returns up to 10 expenses."""
    from app import _extract_query_data
    today = date.today()
    with flask_app.app_context():
        u = _make_user()
        cat = _make_cat(u.id, 'Разное')
        for i in range(12):
            _make_expense(u.id, cat.id, 100 + i, today, description=f'item{i}')
        db.session.commit()

        cats = Category.query.filter_by(user_id=u.id).all()
        result = _extract_query_data('покажи последние траты', u.id, cats)

    assert 'QUERY DATA' in result
    # 10 expense lines (each starts with "ID:")
    assert result.count('ID:') == 10


def test_recent_query_custom_n():
    """'последние 5 расходов' returns exactly 5 expense lines."""
    from app import _extract_query_data
    today = date.today()
    with flask_app.app_context():
        u = _make_user()
        cat = _make_cat(u.id, 'Разное')
        for i in range(8):
            _make_expense(u.id, cat.id, 200 + i, today, description=f'x{i}')
        db.session.commit()

        cats = Category.query.filter_by(user_id=u.id).all()
        result = _extract_query_data('последние 5 расходов', u.id, cats)

    assert result.count('ID:') == 5


def test_comparison_query_two_months():
    """Message with two month names returns comparison block."""
    from app import _extract_query_data
    today = date.today()
    with flask_app.app_context():
        u = _make_user()
        cat = _make_cat(u.id, 'Кафе')
        _make_expense(u.id, cat.id, 3000, date(today.year, 3, 15))
        _make_expense(u.id, cat.id, 4000, date(today.year, 4, 15))
        db.session.commit()

        cats = Category.query.filter_by(user_id=u.id).all()
        result = _extract_query_data('сравни март и апрель', u.id, cats)

    assert 'QUERY DATA' in result
    assert 'март' in result.lower() or 'Март' in result
    assert 'апрель' in result.lower() or 'Апрель' in result
    assert 'Изменение' in result


def test_savings_query():
    """Message about savings returns account balances."""
    from app import _extract_query_data
    with flask_app.app_context():
        u = _make_user()
        acc = SavingsAccount(
            user_id=u.id, name='Отпуск',
            color='#0d6efd', icon='bi-piggy-bank',
            target_amount=100000, is_active=True,
        )
        db.session.add(acc)
        db.session.commit()

        cats = Category.query.filter_by(user_id=u.id).all()
        result = _extract_query_data('сколько на накоплениях', u.id, cats)

    assert 'QUERY DATA' in result
    assert 'Отпуск' in result
    assert '₽' in result


def test_no_query_on_write_message():
    """'добавь расход 500 еда' returns empty string — no query injection."""
    from app import _extract_query_data
    with flask_app.app_context():
        u = _make_user()
        cat = _make_cat(u.id, 'Еда')
        db.session.commit()
        cats = Category.query.filter_by(user_id=u.id).all()
        result = _extract_query_data('добавь расход 500 еда', u.id, cats)

    assert result == ''


def test_no_query_on_greeting():
    """'привет' returns empty string."""
    from app import _extract_query_data
    with flask_app.app_context():
        u = _make_user()
        db.session.commit()
        result = _extract_query_data('привет', u.id, [])

    assert result == ''
```

- [ ] **Step 2: Run to verify all 8 tests fail**

```bash
cd /Users/k1n4_l0v3d/Desktop/expence_tracker-main
source venv/bin/activate
pytest tests/test_chat_queries.py -v 2>&1 | tail -15
```

Expected: 8 FAILED — `ImportError: cannot import name '_extract_query_data'`

---

## Task 2: Implement `_extract_query_data` and helpers

**Files:**
- Modify: `app.py` — after `_RU_MONTH_MAP` block (~line 2400)

- [ ] **Step 1: Add `_RU_MONTH_NAMES` constant and 5 helper functions**

In `app.py`, after the `_RU_MONTH_MAP` dict (after line ≈ 2400), before `def _parse_date`, insert:

```python
_RU_MONTH_NAMES = {
    1: 'январь', 2: 'февраль', 3: 'март', 4: 'апрель',
    5: 'май', 6: 'июнь', 7: 'июль', 8: 'август',
    9: 'сентябрь', 10: 'октябрь', 11: 'ноябрь', 12: 'декабрь',
}


def _qdata_category_month(user_id: int, cat, month: int, year: int) -> str:
    month_start = date(year, month, 1)
    month_end   = date(year, month, calendar.monthrange(year, month)[1])
    total = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.user_id == user_id,
        Expense.category_id == cat.id,
        Expense.is_spent.is_(True),
        Expense.expense_date.between(month_start, month_end),
    ).scalar())
    count = Expense.query.filter(
        Expense.user_id == user_id,
        Expense.category_id == cat.id,
        Expense.is_spent.is_(True),
        Expense.expense_date.between(month_start, month_end),
    ).count()
    return (
        f"\nQUERY DATA (расходы по категории):\n"
        f"{cat.name}, {_RU_MONTH_NAMES[month]} {year}: {total:.0f} ₽ ({count} оп.)"
    )


def _qdata_monthly_summary(user_id: int, month: int, year: int) -> str:
    summary = get_monthly_summary(user_id, year, month)
    income  = get_monthly_income(user_id, year, month)
    total_exp = sum(float(r.total) for r in summary)
    lines = [
        f"\nQUERY DATA (сводка за месяц):",
        f"{_RU_MONTH_NAMES[month].capitalize()} {year} | "
        f"доходы: {income:.0f} ₽ | расходы: {total_exp:.0f} ₽ | остаток: {income - total_exp:.0f} ₽",
    ]
    for r in summary:
        if float(r.total) > 0:
            lines.append(f"  {r.name:<20} {float(r.total):>8.0f} ₽")
    return '\n'.join(lines)


def _qdata_recent(user_id: int, n: int) -> str:
    exps = (Expense.query
        .filter_by(user_id=user_id)
        .order_by(Expense.expense_date.desc(), Expense.id.desc())
        .limit(n).all())
    lines = [f"\nQUERY DATA (последние {n} расходов):"]
    for e in exps:
        desc = e.description or '—'
        lines.append(
            f"ID:{e.id} {float(e.amount):.0f}₽ {e.category.name} {desc} {e.expense_date:%d.%m.%Y}"
        )
    return '\n'.join(lines)


def _qdata_comparison(user_id: int, m1: tuple, m2: tuple) -> str:
    def _totals(month, year):
        s   = get_monthly_summary(user_id, year, month)
        inc = get_monthly_income(user_id, year, month)
        exp = sum(float(r.total) for r in s)
        return inc, exp

    inc1, exp1 = _totals(m1[0], m1[1])
    inc2, exp2 = _totals(m2[0], m2[1])

    if exp1 > 0:
        pct = (exp2 - exp1) / exp1 * 100
        delta = f"+{pct:.1f}%" if pct >= 0 else f"{pct:.1f}%"
    else:
        delta = "н/д"

    return '\n'.join([
        f"\nQUERY DATA (сравнение месяцев):",
        f"{_RU_MONTH_NAMES[m1[0]].capitalize()} {m1[1]}: расходы {exp1:.0f} ₽, доходы {inc1:.0f} ₽",
        f"{_RU_MONTH_NAMES[m2[0]].capitalize()} {m2[1]}: расходы {exp2:.0f} ₽, доходы {inc2:.0f} ₽",
        f"Изменение расходов: {delta}",
    ])


def _qdata_savings(user_id: int) -> str:
    accounts = SavingsAccount.query.filter_by(user_id=user_id, is_active=True).all()
    if not accounts:
        return "\nQUERY DATA (накопления):\nНакопительных счетов нет."
    lines = ["\nQUERY DATA (накопления):"]
    for acc in accounts:
        bal = get_account_balance(acc.id)
        if acc.target_amount and float(acc.target_amount) > 0:
            pct = round(bal / float(acc.target_amount) * 100, 1)
            lines.append(
                f"{acc.name}: {bal:.0f} ₽ (цель {float(acc.target_amount):.0f} ₽, {pct}%)"
            )
        else:
            lines.append(f"{acc.name}: {bal:.0f} ₽")
    return '\n'.join(lines)


def _extract_query_data(message: str, user_id: int, categories: list) -> str:
    """Detect query intent, run DB query, return QUERY DATA block for the system prompt."""
    today = date.today()
    msg   = message.lower().strip()

    # 1. Detect months (up to 2)
    detected_months: list = []
    for prefix, month_num in _RU_MONTH_MAP.items():
        if prefix in msg:
            year = today.year if month_num <= today.month else today.year - 1
            entry = (month_num, year)
            if entry not in detected_months:
                detected_months.append(entry)

    # 2. Detect category
    detected_cat = _find_category_by_name(msg, categories)

    # 3. Keyword flags
    is_savings_q  = any(k in msg for k in ('накоплени', 'сбережени', 'счёт', 'счет', 'баланс'))
    is_recent_q   = any(k in msg for k in ('последни', 'покажи', 'что купил', 'что потратил', 'что брал', 'история'))
    is_query_word = any(k in msg for k in ('сколько', 'итого', 'всего', 'топ', 'больше всего',
                                            'на что', 'сводк', 'потратил', 'расход', 'ушло', 'трат'))
    is_compare    = (len(detected_months) >= 2 or
                     ('сравни' in msg and len(detected_months) >= 1))

    # 4. Branch
    if is_savings_q:
        return _qdata_savings(user_id)

    if is_compare:
        months = detected_months[:2]
        if len(months) == 1:
            months.append((today.month, today.year))
        return _qdata_comparison(user_id, months[0], months[1])

    if is_recent_q:
        nums = re.findall(r'\d+', msg)
        n = min(int(nums[0]), 20) if nums else 10
        return _qdata_recent(user_id, n)

    if detected_cat and detected_months and is_query_word:
        m, y = detected_months[0]
        return _qdata_category_month(user_id, detected_cat, m, y)

    if detected_months and is_query_word:
        m, y = detected_months[0]
        return _qdata_monthly_summary(user_id, m, y)

    return ''
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_chat_queries.py -v 2>&1 | tail -15
```

Expected: 8 PASSED

- [ ] **Step 3: Run full suite to confirm no regressions**

```bash
pytest tests/ -q 2>&1 | tail -4
```

Expected: all tests pass (86 + 8 = 94 total)

- [ ] **Step 4: Commit**

```bash
git add app.py tests/test_chat_queries.py
git commit -m "feat: add _extract_query_data and query helper functions"
```

---

## Task 3: Wire `_build_system_prompt` and `api_chat()`

**Files:**
- Modify: `app.py` — `_build_system_prompt` signature (~line 2471); `api_chat()` (~line 2763)

- [ ] **Step 1: Update `_build_system_prompt` — 3 surgical edits**

**Edit A** — function signature. Find:
```python
def _build_system_prompt(ctx: dict) -> str:
```
Replace with:
```python
def _build_system_prompt(ctx: dict, query_data: str = '') -> str:
```

**Edit B** — add rule 8 to the RULES block. Find the existing rule 7 line:
```
7. Recent records = for edit/delete reference only. Ignore them for add requests.
```
Replace with:
```
7. Recent records = for edit/delete reference only. Ignore them for add requests.
8. If QUERY DATA is present below, use it to answer the question. Do NOT invent numbers.
```

**Edit C** — change the return statement. Find the last line of the function:
```python
    return f"""Financial assistant. Respond ONLY in Russian. ...
...
{inc_lines}"""
```
The final line of the f-string ends exactly with `{inc_lines}"""`. Change it to capture in a variable and append `query_data`:
```python
    base = f"""Financial assistant. Respond ONLY in Russian. ...
...
{inc_lines}"""
    return base + query_data
```
(Only the `return` → `base =` change plus adding `return base + query_data` at the end. All content between is unchanged.)

- [ ] **Step 2: Update `api_chat()` to call `_extract_query_data`**

In `api_chat()`, find these two lines (≈ line 2763 + offset):

```python
        ctx = _build_chat_context(current_user.id)
        system_prompt = _build_system_prompt(ctx)
```

Replace with:

```python
        ctx          = _build_chat_context(current_user.id)
        query_data   = _extract_query_data(user_message, current_user.id, ctx['categories'])
        system_prompt = _build_system_prompt(ctx, query_data)
```

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -q 2>&1 | tail -4
```

Expected: 94 passed (86 existing + 8 new)

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: wire _extract_query_data into api_chat system prompt"
```

---

## Task 4: Final smoke test

- [ ] **Step 1: Verify app starts**

```bash
source venv/bin/activate && python -c "from app import app, _extract_query_data; print('OK')"
```

Expected: `OK`

- [ ] **Step 2: Run complete test suite**

```bash
pytest tests/ -v 2>&1 | tail -20
```

Expected: 94 passed, 0 failed.

- [ ] **Step 3: Push to GitHub**

```bash
git push origin main
```
