# Stats Section Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two statistics sections to the bottom of the Overview page: category comparison (vs previous month or same month last year) and a 3-month dynamics block.

**Architecture:** New `/api/stats-data` endpoint in `app.py` returns JSON with comparison and monthly data. Two new HTML sections added to `templates/index.html` render the data via JavaScript. New CSS rules in `static/css/style.css` handle both light and dark themes.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, Bootstrap 5.3, Vanilla JS, Bootstrap Icons

---

### Task 1: Add `/api/stats-data` endpoint to app.py

**Files:**
- Modify: `app.py` (add route after existing `/api/chart-data` route, around line 650)

- [ ] **Step 1: Add the helper functions and route**

Add the following code to `app.py` after the `chart_data` route (after line 650, before `with app.app_context()`):

```python
def _prev_period(year: int, month: int, mode: str):
    """Return (year, month) of the comparison period."""
    if mode == 'prev_year':
        return year - 1, month
    # prev_month
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _month_label(year: int, month: int) -> str:
    MONTHS_RU = [
        '', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
        'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
    ]
    return f'{MONTHS_RU[month]} {year}'


@app.route('/api/stats-data')
@login_required
def stats_data():
    today = date.today()
    year  = int(request.args.get('year',  today.year))
    month = int(request.args.get('month', today.month))
    mode  = request.args.get('mode', 'prev_month')  # 'prev_month' | 'prev_year'
    uid   = current_user.id

    # ── Comparison block ──────────────────────────────────────────────
    py, pm = _prev_period(year, month, mode)

    # Expenses per category for current and comparison period
    def cat_totals(y, m):
        rows = (
            db.session.query(
                Category.id,
                Category.name,
                Category.color,
                Category.icon,
                func.coalesce(func.sum(Expense.amount), 0).label('total'),
            )
            .outerjoin(
                Expense,
                (Expense.category_id == Category.id)
                & (Expense.user_id == uid)
                & (extract('year',  Expense.expense_date) == y)
                & (extract('month', Expense.expense_date) == m),
            )
            .filter(Category.is_active.is_(True))
            .group_by(Category.id, Category.name, Category.color, Category.icon)
            .all()
        )
        return {r.id: {'name': r.name, 'color': r.color, 'icon': r.icon, 'total': float(r.total)} for r in rows}

    cur_map  = cat_totals(year, month)
    prev_map = cat_totals(py, pm)

    categories = []
    for cat_id, cur in cur_map.items():
        prev_total = prev_map.get(cat_id, {}).get('total', None)
        if cur['total'] == 0 and (prev_total is None or prev_total == 0):
            continue
        if prev_total is None or prev_total == 0:
            delta_pct = None  # новая категория
        else:
            delta_pct = round((cur['total'] - prev_total) / prev_total * 100, 1)
        categories.append({
            'id':        cat_id,
            'name':      cur['name'],
            'color':     cur['color'],
            'icon':      cur['icon'],
            'current':   cur['total'],
            'previous':  prev_total or 0,
            'delta_pct': delta_pct,
        })

    categories.sort(key=lambda x: x['current'], reverse=True)

    total_cur  = sum(c['current']  for c in categories)
    total_prev = sum(c['previous'] for c in categories)
    total_delta = round((total_cur - total_prev) / total_prev * 100, 1) if total_prev else None

    # ── Monthly dynamics (last 3 months) ─────────────────────────────
    months_data = []
    cy, cm = year, month
    for i in range(3):
        inc = float(db.session.query(
            func.coalesce(func.sum(Income.amount), 0)
        ).filter(
            Income.user_id == uid,
            extract('year',  Income.income_date) == cy,
            extract('month', Income.income_date) == cm,
        ).scalar())
        exp = float(db.session.query(
            func.coalesce(func.sum(Expense.amount), 0)
        ).filter(
            Expense.user_id == uid,
            extract('year',  Expense.expense_date) == cy,
            extract('month', Expense.expense_date) == cm,
        ).scalar())
        months_data.append({
            'year': cy, 'month': cm,
            'label': _month_label(cy, cm),
            'income': inc, 'expenses': exp,
            'balance': round(inc - exp, 2),
            'is_current': (i == 0),
        })
        cy, cm = _prev_period(cy, cm, 'prev_month')

    months_data.reverse()  # хронологический порядок: старый → новый

    # % изменения относительно предыдущего месяца в списке
    for i in range(1, len(months_data)):
        prev = months_data[i - 1]
        cur  = months_data[i]
        cur['income_delta']  = round((cur['income']   - prev['income'])   / prev['income']   * 100, 1) if prev['income']   else None
        cur['expense_delta'] = round((cur['expenses'] - prev['expenses']) / prev['expenses'] * 100, 1) if prev['expenses'] else None

    # Тренды
    best_income  = max(months_data, key=lambda x: x['income'])
    worst_expense = max(months_data, key=lambda x: x['expenses'])
    best_balance = max(months_data, key=lambda x: x['balance'])

    return jsonify({
        'comparison': {
            'mode':          mode,
            'current_label': _month_label(year, month),
            'compare_label': _month_label(py, pm),
            'categories':    categories,
            'total_current': round(total_cur,  2),
            'total_previous': round(total_prev, 2),
            'total_delta':   total_delta,
        },
        'monthly': {
            'months': months_data,
            'best_income_month':   {'label': best_income['label'],   'amount': best_income['income']},
            'worst_expense_month': {'label': worst_expense['label'], 'amount': worst_expense['expenses']},
            'best_balance_month':  {'label': best_balance['label'],  'amount': best_balance['balance']},
        },
    })
```

- [ ] **Step 2: Проверить, что Flask запускается без ошибок**

```
python app.py
```

Ожидаемый результат: сервер стартует на `http://127.0.0.1:5000`

---

### Task 2: Добавить CSS в style.css

**Files:**
- Modify: `static/css/style.css` (добавить в конец файла)

- [ ] **Step 1: Добавить стили в конец `static/css/style.css`**

```css
/* ══════════════════════════════════════════
   БЛОК СТАТИСТИКИ — СРАВНЕНИЕ И ДИНАМИКА
══════════════════════════════════════════ */

/* Переключатель режима сравнения */
.compare-toggle .btn {
    border-radius: 20px;
    font-size: 0.8rem;
    padding: 4px 14px;
    transition: background 0.2s, color 0.2s, border-color 0.2s;
}
.compare-toggle .btn.active-mode {
    background: var(--bs-primary);
    color: #fff;
    border-color: var(--bs-primary);
}
.compare-toggle .btn:not(.active-mode) {
    background: transparent;
    color: var(--bs-secondary-color);
    border-color: var(--bs-border-color);
}

/* Строка категории */
.cat-stat-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 0;
    border-bottom: 1px solid var(--bs-border-color);
}
.cat-stat-row:last-child { border-bottom: none; }

.cat-stat-icon {
    width: 34px;
    height: 34px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1rem;
    flex-shrink: 0;
}
.cat-stat-name   { flex: 1; font-weight: 500; font-size: 0.92rem; }
.cat-stat-amount { min-width: 90px; text-align: right; font-weight: 600; font-size: 0.92rem; }
.cat-stat-delta  { min-width: 78px; text-align: right; }

/* Бейдж дельты */
.delta-badge {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    border-radius: 20px;
    padding: 2px 9px;
    font-size: 0.8rem;
    font-weight: 600;
    background: var(--bs-secondary-bg);
}
.delta-up   { color: #dc3545; }
.delta-down { color: #198754; }
.delta-new  { color: #fd7e14; }
.delta-zero { color: var(--bs-secondary-color); }

/* Итоговая строка сравнения */
.stat-trend-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    border-radius: 10px;
    background: var(--bs-secondary-bg);
    margin-bottom: 6px;
}
.stat-trend-row:last-child { margin-bottom: 0; }
.stat-trend-label { flex: 1; font-size: 0.88rem; color: var(--bs-secondary-color); }
.stat-trend-val   { font-weight: 700; font-size: 0.92rem; }

/* Карточки 3-месячной динамики */
.month-stat-wrap { display: flex; gap: 12px; }
.month-stat-col  { flex: 1; min-width: 0; }
.month-stat-label {
    font-size: 0.75rem;
    color: var(--bs-secondary-color);
    margin-bottom: 6px;
    text-align: center;
    text-transform: uppercase;
    letter-spacing: .05em;
}
.month-stat-card {
    border-radius: 12px;
    padding: 12px 14px;
    text-align: center;
    border: 1px solid var(--bs-border-color);
    background: var(--bs-body-bg);
}
.month-stat-card.is-current {
    border-color: var(--bs-primary);
    background: var(--bs-primary-bg-subtle);
}
.month-income-val  { font-size: 0.82rem; font-weight: 600; color: #198754; }
.month-expense-val { font-size: 0.82rem; font-weight: 600; color: #dc3545; }
.month-balance-val { font-size: 0.75rem; color: var(--bs-secondary-color); margin-top: 4px; }
.month-delta-wrap  {
    display: flex;
    gap: 4px;
    align-items: center;
    justify-content: center;
    margin-top: 5px;
    flex-wrap: wrap;
}
.month-delta-inc  { font-size: 0.7rem; font-weight: 600; color: #198754; }
.month-delta-exp  { font-size: 0.7rem; font-weight: 600; color: #dc3545; }

/* Секция-инфо: "сравниваем X с Y" */
.stats-note {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: var(--bs-primary-bg-subtle);
    border: 1px solid var(--bs-primary-border-subtle);
    border-radius: 20px;
    padding: 4px 12px;
    font-size: 0.8rem;
    color: var(--bs-primary);
    margin-bottom: 14px;
}

/* ── DARK MODE overrides ── */
[data-bs-theme="dark"] .delta-up   { color: #ff6b81; }
[data-bs-theme="dark"] .delta-down { color: #00ffb8; }
[data-bs-theme="dark"] .delta-new  { color: #ffd166; }

[data-bs-theme="dark"] .month-income-val  { color: #00ffb8; }
[data-bs-theme="dark"] .month-expense-val { color: #ff6b81; }

[data-bs-theme="dark"] .month-stat-card.is-current {
    border-color: #4361ee;
    background: rgba(67, 97, 238, 0.12);
    box-shadow: 0 0 14px rgba(67, 97, 238, 0.25);
}

[data-bs-theme="dark"] .stats-note {
    background: rgba(67, 97, 238, 0.12);
    border-color: rgba(67, 97, 238, 0.35);
    color: #a0b4ff;
}

/* Мобильная адаптация карточек динамики */
@media (max-width: 575.98px) {
    .month-stat-wrap { gap: 8px; }
    .month-stat-card { padding: 10px 8px; }
    .month-income-val,
    .month-expense-val { font-size: 0.75rem; }
    .month-balance-val { font-size: 0.68rem; }
    .cat-stat-amount   { min-width: 70px; }
    .cat-stat-delta    { min-width: 60px; }
}
```

---

### Task 3: Добавить HTML-секции в index.html

**Files:**
- Modify: `templates/index.html` (добавить перед `{% endblock %}` основного контента, после закрывающего `</div>` строки 168)

- [ ] **Step 1: Вставить два новых блока перед `{% endblock %}`**

Вставить после строки 168 (`</div>` закрывающего `row g-4`), перед `{% endblock %}`:

```html
<!-- ══════════════════════════════════════════════════════════════════
     БЛОК 1 — Сравнение по категориям
════════════════════════════════════════════════════════════════════ -->
<div class="row g-4 mt-2">
    <div class="col-lg-7">
        <div class="card shadow-sm border-0 h-100" id="comparisonCard">
            <div class="card-header bg-body fw-semibold border-0 pt-3 d-flex align-items-center justify-content-between flex-wrap gap-2">
                <span><i class="bi bi-arrow-left-right text-primary me-2"></i>Сравнение по категориям</span>
                <div class="compare-toggle d-flex gap-2">
                    <button class="btn btn-sm active-mode" id="btnPrevMonth" type="button">vs прошлый месяц</button>
                    <button class="btn btn-sm" id="btnPrevYear" type="button">vs прошлый год</button>
                </div>
            </div>
            <div class="card-body">
                <div class="stats-note" id="compareNote">
                    <i class="bi bi-info-circle"></i>
                    Сравниваем <strong id="compareCurrent"></strong> с <strong id="compareWith"></strong>
                </div>
                <div id="catCompareList">
                    <!-- Skeleton -->
                    <div class="skeleton mb-2" style="height:40px;border-radius:8px"></div>
                    <div class="skeleton mb-2" style="height:40px;border-radius:8px"></div>
                    <div class="skeleton mb-2" style="height:40px;border-radius:8px"></div>
                </div>
                <div class="mt-3 pt-2 border-top" id="compareTotalRow" style="display:none">
                    <div class="stat-trend-row">
                        <span class="stat-trend-label"><i class="bi bi-sigma me-2 text-primary"></i>Итого расходов</span>
                        <span class="stat-trend-val" id="compareTotalVal"></span>
                        <span id="compareTotalDelta"></span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- ══════════════════════════════════════════════════════════════
         БЛОК 2 — Динамика за 3 месяца
    ═══════════════════════════════════════════════════════════════ -->
    <div class="col-lg-5">
        <div class="card shadow-sm border-0 h-100">
            <div class="card-header bg-body fw-semibold border-0 pt-3">
                <i class="bi bi-calendar3 text-primary me-2"></i>Динамика за 3 месяца
            </div>
            <div class="card-body">
                <div class="month-stat-wrap mb-3" id="monthDynamics">
                    <div class="skeleton" style="flex:1;height:100px;border-radius:12px"></div>
                    <div class="skeleton" style="flex:1;height:100px;border-radius:12px"></div>
                    <div class="skeleton" style="flex:1;height:100px;border-radius:12px"></div>
                </div>
                <div class="small text-uppercase text-muted fw-semibold mb-2" style="letter-spacing:.06em">Тренды за период</div>
                <div id="monthTrends">
                    <div class="skeleton mb-2" style="height:36px;border-radius:8px"></div>
                    <div class="skeleton mb-2" style="height:36px;border-radius:8px"></div>
                    <div class="skeleton" style="height:36px;border-radius:8px"></div>
                </div>
            </div>
        </div>
    </div>
</div>
```

---

### Task 4: Добавить JS в блок scripts в index.html

**Files:**
- Modify: `templates/index.html` (добавить в `{% block scripts %}` после существующего JS)

- [ ] **Step 1: Добавить JS после строки с `_themeObserver.observe`**

Добавить в конец блока `{% block scripts %}`, перед закрывающим `</script>`:

```javascript
// ── Статистика: сравнение и динамика ──────────────────────────────
let _statsMode = 'prev_month';

function fmtRub(val) {
    return val.toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + ' ₽';
}

function deltaBadgeHtml(delta) {
    if (delta === null || delta === undefined) {
        return '<span class="delta-badge delta-new"><i class="bi bi-plus-circle"></i> новая</span>';
    }
    if (delta === 0) {
        return '<span class="delta-badge delta-zero">0%</span>';
    }
    const sign  = delta > 0 ? '+' : '';
    const cls   = delta > 0 ? 'delta-up' : 'delta-down';
    const arrow = delta > 0 ? 'bi-arrow-up' : 'bi-arrow-down';
    return `<span class="delta-badge ${cls}"><i class="bi ${arrow}"></i>${sign}${delta}%</span>`;
}

function renderStats(data) {
    const cmp = data.comparison;
    const mon = data.monthly;

    // Заголовок сравнения
    document.getElementById('compareCurrent').textContent = cmp.current_label;
    document.getElementById('compareWith').textContent    = cmp.compare_label;

    // Список категорий
    const listEl = document.getElementById('catCompareList');
    if (!cmp.categories.length) {
        listEl.innerHTML = '<p class="text-muted text-center py-3">Данных для сравнения нет</p>';
    } else {
        listEl.innerHTML = cmp.categories.map(c => `
            <div class="cat-stat-row stagger-item">
                <div class="cat-stat-icon" style="background:${c.color}22">
                    <i class="bi ${c.icon}" style="color:${c.color}"></i>
                </div>
                <div class="cat-stat-name">${c.name}</div>
                <div class="cat-stat-amount">${fmtRub(c.current)}</div>
                <div class="cat-stat-delta">${deltaBadgeHtml(c.delta_pct)}</div>
            </div>
        `).join('');
        // Запускаем stagger-анимацию
        listEl.querySelectorAll('.stagger-item').forEach((el, i) => {
            el.style.setProperty('--i', i);
            setTimeout(() => el.classList.add('stagger-visible'), 10);
        });
    }

    // Итого
    const totalRow = document.getElementById('compareTotalRow');
    totalRow.style.display = '';
    document.getElementById('compareTotalVal').textContent = fmtRub(cmp.total_current);
    document.getElementById('compareTotalDelta').innerHTML = deltaBadgeHtml(cmp.total_delta);

    // Карточки месяцев
    const dynEl = document.getElementById('monthDynamics');
    dynEl.innerHTML = mon.months.map(m => {
        const incDelta = m.income_delta !== undefined
            ? `<span class="month-delta-inc"><i class="bi bi-arrow-${m.income_delta >= 0 ? 'up' : 'down'}"></i>доходы ${m.income_delta >= 0 ? '+' : ''}${m.income_delta}%</span>` : '';
        const expDelta = m.expense_delta !== undefined
            ? `<span class="month-delta-exp"><i class="bi bi-arrow-${m.expense_delta >= 0 ? 'up' : 'down'}"></i>расходы ${m.expense_delta >= 0 ? '+' : ''}${m.expense_delta}%</span>` : '';
        const deltaWrap = (incDelta || expDelta)
            ? `<div class="month-delta-wrap">${incDelta}${expDelta}</div>` : '';
        return `
            <div class="month-stat-col">
                <div class="month-stat-label${m.is_current ? ' fw-bold text-primary' : ''}">${m.label}</div>
                <div class="month-stat-card${m.is_current ? ' is-current' : ''}">
                    <div class="month-income-val"><i class="bi bi-arrow-down-circle me-1"></i>${fmtRub(m.income)}</div>
                    <div class="month-expense-val"><i class="bi bi-arrow-up-circle me-1"></i>${fmtRub(m.expenses)}</div>
                    <div class="month-balance-val">баланс ${m.balance >= 0 ? '+' : ''}${fmtRub(m.balance)}</div>
                    ${deltaWrap}
                </div>
            </div>
        `;
    }).join('');

    // Тренды
    document.getElementById('monthTrends').innerHTML = `
        <div class="stat-trend-row">
            <span class="stat-trend-label"><i class="bi bi-graph-up-arrow me-2" style="color:#198754"></i>Лучший месяц по доходам</span>
            <span class="stat-trend-val" style="color:#198754">${mon.best_income_month.label} — ${fmtRub(mon.best_income_month.amount)}</span>
        </div>
        <div class="stat-trend-row">
            <span class="stat-trend-label"><i class="bi bi-graph-down-arrow me-2" style="color:#dc3545"></i>Месяц с наибольшими расходами</span>
            <span class="stat-trend-val" style="color:#dc3545">${mon.worst_expense_month.label} — ${fmtRub(mon.worst_expense_month.amount)}</span>
        </div>
        <div class="stat-trend-row">
            <span class="stat-trend-label"><i class="bi bi-piggy-bank me-2 text-primary"></i>Лучший баланс</span>
            <span class="stat-trend-val text-primary">${mon.best_balance_month.label} — ${fmtRub(mon.best_balance_month.amount)}</span>
        </div>
    `;
}

function loadStats(mode) {
    _statsMode = mode;
    // Кнопки
    document.getElementById('btnPrevMonth').classList.toggle('active-mode', mode === 'prev_month');
    document.getElementById('btnPrevYear').classList.toggle('active-mode', mode === 'prev_year');

    fetch(`/api/stats-data?year={{ year }}&month={{ month }}&mode=${mode}`)
        .then(r => r.json())
        .then(renderStats);
}

document.getElementById('btnPrevMonth').addEventListener('click', () => loadStats('prev_month'));
document.getElementById('btnPrevYear').addEventListener('click',  () => loadStats('prev_year'));

// Загружаем при старте
loadStats('prev_month');
```

- [ ] **Step 2: Открыть браузер и проверить страницу**

Открыть `http://127.0.0.1:5000/` — убедиться что два новых блока появляются внизу страницы.

- [ ] **Step 3: Переключить тему (кнопка в navbar) — убедиться что оба блока корректно выглядят в светлой и тёмной теме**

- [ ] **Step 4: Проверить на мобильном (DevTools → Toggle device toolbar) — карточки и таблица должны адаптироваться под узкий экран**
