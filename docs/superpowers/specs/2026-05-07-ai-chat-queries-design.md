# AI Chat Query Support — Design Spec

**Date:** 2026-05-07
**Status:** Approved

---

## Problem

The AI chat can add/edit/delete expenses, income, savings and budgets, but cannot answer analytical questions about existing data. Queries like "сколько потратил на еду в апреле?" or "покажи последние 10 трат" return either a wrong answer (hallucinated numbers) or a refusal.

## Solution

Before calling Groq, detect query intent from the user message, run the relevant SQL query server-side, and inject the results as a `QUERY DATA:` block into the system prompt. Groq formats the data into a readable Russian response using the existing `none()` action. Numbers always come from the DB — no hallucination possible.

---

## Supported Query Types

| Pattern detected | Data fetched |
|---|---|
| Category name + month | `SUM(amount)` for that category and month |
| "больше всего" / "топ" / "на что" + optional month | Full category breakdown for the month |
| "последние N" / "покажи траты" / "что покупал" | Last N expenses (default 10, max 20) |
| "сколько за [месяц]" / "итого" / "всего потратил" | Income + expenses totals for the month |
| "сравни [месяц1] и [месяц2]" / two month names | Category breakdowns for both months + delta |
| "накоплени" / "сбережени" / "счёт" / "баланс" | All savings accounts with balances and progress |

If no query pattern is detected the function returns an empty string and the prompt is unchanged.

---

## Backend (`app.py`)

### New function: `_extract_query_data(message, user_id, categories)`

```python
def _extract_query_data(message: str, user_id: int, categories: list) -> str:
    ...
```

**Returns:** a formatted string starting with `\nQUERY DATA` to append to the system prompt, or `""` if no query detected.

#### Detection logic (in order)

1. **Normalize:** `msg = message.lower().strip()`

2. **Detect months:** scan `msg` against `_RU_MONTH_MAP` prefixes. Collect up to 2 month numbers found. Use `date.today().year` as default year (adjust to previous year if month > today.month and only one month found — avoids future dates).

3. **Detect category:** call `_find_category_by_name()` against each token/phrase. Use the first match.

4. **Detect query type** (checked in order):
   - **comparison:** count of detected months == 2 (two distinct month names found); if `"сравни" in msg` but only one month found, compare that month with the current month
   - **savings:** any of `("накоплени", "сбережени", "счёт", "баланс")` in msg
   - **recent:** any of `("последни", "покажи", "что купил", "что потратил", "что брал", "история")` in msg
   - **category+month:** category found AND month found AND any of `("сколько", "потратил", "расход", "ушло", "трат")`
   - **monthly summary:** month found AND any of `("сколько", "итого", "всего", "топ", "больше всего", "на что", "сводк")`
   - **None:** return `""`

5. **Parse N for recent:** scan `msg` for digits (`\d+`), take first value clamped to [1, 20], default 10.

#### DB queries per type

**`category_month`:**
```python
month_start = date(year, month, 1)
month_end   = date(year, month, calendar.monthrange(year, month)[1])
total = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
    Expense.user_id == user_id,
    Expense.category_id == cat.id,
    Expense.is_spent.is_(True),
    Expense.expense_date.between(month_start, month_end),
).scalar()
count = Expense.query.filter(...).count()
# Returns: "QUERY DATA (расходы по категории):\n{cat} {month_name} {year}: {total:.0f} ₽ ({count} оп.)"
```

**`monthly_summary`:**
```python
summary = get_monthly_summary(user_id, year, month)   # existing helper
income  = get_monthly_income(user_id, year, month)    # existing helper
# Returns multi-line: header + per-category rows sorted by amount desc
```

**`recent`:**
```python
exps = (Expense.query
    .filter_by(user_id=user_id)
    .order_by(Expense.expense_date.desc(), Expense.id.desc())
    .limit(n).all())
# Returns: "QUERY DATA (последние {n} расходов):\n" + one line per expense
# Line format: "ID:{id} {amount:.0f}₽ {category} {description or '—'} {date:%d.%m.%Y}"
```

**`comparison`:**
```python
# Run monthly_summary for each of the two months
# Compute total delta %
# Returns: two summary blocks + "Изменение расходов: ±X%"
```

**`savings`:**
```python
accounts = SavingsAccount.query.filter_by(user_id=user_id, is_active=True).all()
for acc in accounts:
    bal = get_account_balance(acc.id)   # existing helper
# Returns: one line per account: "Name: {bal:.0f} ₽" + optional "(цель X ₽, Y%)"
```

---

### Updated: `_build_system_prompt(ctx, query_data="")`

Add `query_data: str = ""` parameter. At the end of the returned string, append:

```python
if query_data:
    return base_prompt + query_data
return base_prompt
```

---

### Updated: `api_chat()`

One new line before `system_prompt = _build_system_prompt(ctx)`:

```python
query_data   = _extract_query_data(user_message, current_user.id, ctx['categories'])
system_prompt = _build_system_prompt(ctx, query_data)
```

---

## Example injected blocks

**Category + month:**
```
QUERY DATA (расходы по категории):
Еда, апрель 2026: 4 820 ₽ (7 оп.)
```

**Monthly summary:**
```
QUERY DATA (сводка за месяц):
Апрель 2026 | доходы: 85 000 ₽ | расходы: 42 300 ₽ | остаток: 42 700 ₽
  Еда            12 400 ₽  (18 оп.)
  Транспорт       8 200 ₽  (9 оп.)
  Развлечения     6 100 ₽  (5 оп.)
```

**Recent:**
```
QUERY DATA (последние 10 расходов):
ID:142 1 200₽ Еда Пятёрочка 06.05.2026
ID:141   450₽ Транспорт Метро 06.05.2026
```

**Comparison:**
```
QUERY DATA (сравнение месяцев):
Март 2026: расходы 38 100 ₽, доходы 80 000 ₽
Апрель 2026: расходы 42 300 ₽, доходы 85 000 ₽
Изменение расходов: +10.8%
```

**Savings:**
```
QUERY DATA (накопления):
Отпуск: 45 200 ₽ (цель 100 000 ₽, 45%)
Авто: 120 000 ₽ (цель 500 000 ₽, 24%)
```

---

## Testing (`tests/test_chat_queries.py`)

Unit-test `_extract_query_data` directly — no Groq calls needed.

| Test | Input message | Expected output contains |
|---|---|---|
| `test_category_month_query` | "сколько потратил на еду в апреле" | "QUERY DATA", category name, "₽" |
| `test_monthly_summary_query` | "сколько потратил в мае" | "QUERY DATA", "доходы", "расходы" |
| `test_recent_query_default` | "покажи последние траты" | "QUERY DATA", 10 lines of expenses |
| `test_recent_query_custom_n` | "последние 5 расходов" | exactly 5 expense lines |
| `test_comparison_query` | "сравни апрель и май" | both month names, "Изменение" |
| `test_savings_query` | "сколько на накоплениях" | "QUERY DATA", account names |
| `test_no_query_on_write` | "добавь расход 500 еда" | empty string `""` |
| `test_no_query_generic` | "привет" | empty string `""` |

---

## Out of Scope

- Natural language generation of SQL (no LLM-generated queries)
- Date ranges beyond single months or two-month comparison
- Frontend UI changes (no new message types or tables in chat)
- Caching of query results
