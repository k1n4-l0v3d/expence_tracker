# Daily Budget Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить карточку «Можно тратить в день» на главную страницу — баланс / дней до ближайшей выплаты, с модалкой настройки дат.

**Architecture:** Два поля `salary_day`/`advance_day` в модели `User`, миграция через `ALTER TABLE` при старте (как уже сделано для `avatar`). Новый POST-эндпоинт `/api/payment-days` сохраняет дни. Логика вычисления — helper-функция в `app.py`. Карточка и модалка — в `templates/index.html`.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, Bootstrap 5, vanilla JS (fetch API).

---

### Task 1: Модель — поля + миграция

**Files:**
- Modify: `app.py:99-131` (класс `User`)
- Modify: `app.py:928-937` (блок миграции при старте)

- [ ] **Шаг 1: Добавить поля в модель `User`**

В классе `User` после строки `avatar = db.Column(...)` добавить:

```python
salary_day  = db.Column(db.Integer, nullable=True)
advance_day = db.Column(db.Integer, nullable=True)
```

- [ ] **Шаг 2: Добавить миграцию в блок at startup**

В блоке `with app.app_context():` (строки 928–937) после проверки `avatar` добавить:

```python
if 'salary_day' not in columns:
    with db.engine.connect() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN salary_day INTEGER NULL;"))
        conn.commit()
if 'advance_day' not in columns:
    with db.engine.connect() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN advance_day INTEGER NULL;"))
        conn.commit()
```

- [ ] **Шаг 3: Запустить приложение и убедиться, что колонки появились**

```bash
python3 app.py &
sleep 2
kill %1
```

Ожидаем: приложение стартует без ошибок.

- [ ] **Шаг 4: Коммит**

```bash
git add app.py
git commit -m "feat: add salary_day and advance_day fields to User model"
```

---

### Task 2: Helper-функция вычисления ежедневного бюджета

**Files:**
- Modify: `app.py` (раздел `# ─── Хелперы ───`, после функции `get_budget_map`)
- Test: `tests/test_daily_budget.py`

- [ ] **Шаг 1: Написать тест (падающий)**

Создать файл `tests/test_daily_budget.py`:

```python
import pytest
from datetime import date, timedelta
from unittest.mock import patch


def test_next_payment_date_future():
    """Если день выплаты ещё не наступил в этом месяце — возвращает дату в этом месяце."""
    from app import next_payment_date
    today = date(2026, 4, 18)
    with patch('app.date') as mock_date:
        mock_date.today.return_value = today
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        result = next_payment_date(25)
    assert result == date(2026, 4, 25)


def test_next_payment_date_past():
    """Если день выплаты уже прошёл — возвращает дату в следующем месяце."""
    from app import next_payment_date
    today = date(2026, 4, 18)
    with patch('app.date') as mock_date:
        mock_date.today.return_value = today
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        result = next_payment_date(10)
    assert result == date(2026, 5, 10)


def test_next_payment_date_today():
    """Если день выплаты сегодня — возвращает следующий месяц (сегодня уже 'прошло')."""
    from app import next_payment_date
    today = date(2026, 4, 18)
    with patch('app.date') as mock_date:
        mock_date.today.return_value = today
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        result = next_payment_date(18)
    assert result == date(2026, 5, 18)


def test_next_payment_date_overflow():
    """День 31 в феврале → последний день февраля следующего периода."""
    from app import next_payment_date
    today = date(2026, 2, 5)
    with patch('app.date') as mock_date:
        mock_date.today.return_value = today
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        result = next_payment_date(31)
    assert result == date(2026, 2, 28)


def test_get_daily_budget_no_days():
    """Если обе даты не заданы — возвращает None."""
    from app import get_daily_budget_info
    result = get_daily_budget_info(balance=5000.0, salary_day=None, advance_day=None)
    assert result is None


def test_get_daily_budget_positive():
    """Положительный баланс делится на дни до ближайшей выплаты."""
    from app import get_daily_budget_info
    today = date(2026, 4, 18)
    with patch('app.date') as mock_date:
        mock_date.today.return_value = today
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        # ближайшая: аванс 25 апреля = 7 дней
        result = get_daily_budget_info(balance=700.0, salary_day=None, advance_day=25)
    assert result['daily'] == pytest.approx(100.0)
    assert result['days_left'] == 7
    assert result['payment_type'] == 'аванса'


def test_get_daily_budget_negative():
    """Отрицательный баланс → отрицательная дневная сумма."""
    from app import get_daily_budget_info
    today = date(2026, 4, 18)
    with patch('app.date') as mock_date:
        mock_date.today.return_value = today
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        result = get_daily_budget_info(balance=-700.0, salary_day=25, advance_day=None)
    assert result['daily'] == pytest.approx(-100.0)


def test_get_daily_budget_picks_nearest():
    """Берётся ближайшая из двух дат."""
    from app import get_daily_budget_info
    today = date(2026, 4, 18)
    with patch('app.date') as mock_date:
        mock_date.today.return_value = today
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        # аванс 25 (7 дней), зарплата 10 мая (22 дня) → берём аванс
        result = get_daily_budget_info(balance=700.0, salary_day=10, advance_day=25)
    assert result['days_left'] == 7
    assert result['payment_type'] == 'аванса'
```

- [ ] **Шаг 2: Запустить тесты — убедиться, что падают**

```bash
python3 -m pytest tests/test_daily_budget.py -v
```

Ожидаем: `ImportError: cannot import name 'next_payment_date'`

- [ ] **Шаг 3: Реализовать helper-функции в `app.py`**

В разделе хелперов (`# ─── Хелперы ───`), после функции `get_budget_map`, добавить:

```python
def _last_day_of_month(d: date) -> date:
    next_month = d.replace(day=28) + timedelta(days=4)
    return next_month.replace(day=1) - timedelta(days=1)


def next_payment_date(day: int) -> date:
    today = date.today()
    last = _last_day_of_month(today)
    clamped_day = min(day, last.day)
    candidate = today.replace(day=clamped_day)
    if candidate <= today:
        first_next = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        last_next = _last_day_of_month(first_next)
        candidate = first_next.replace(day=min(day, last_next.day))
    return candidate


def get_daily_budget_info(balance: float, salary_day, advance_day) -> dict | None:
    options = []
    if salary_day:
        options.append((next_payment_date(salary_day), 'зарплаты'))
    if advance_day:
        options.append((next_payment_date(advance_day), 'аванса'))
    if not options:
        return None
    nearest_date, payment_type = min(options, key=lambda x: x[0])
    today = date.today()
    days_left = max((nearest_date - today).days, 1)
    return {
        'daily': round(balance / days_left, 2),
        'days_left': days_left,
        'payment_type': payment_type,
        'nearest_date': nearest_date,
    }
```

- [ ] **Шаг 4: Запустить тесты — убедиться, что проходят**

```bash
python3 -m pytest tests/test_daily_budget.py -v
```

Ожидаем: все 7 тестов `PASSED`.

- [ ] **Шаг 5: Коммит**

```bash
git add app.py tests/test_daily_budget.py
git commit -m "feat: add next_payment_date and get_daily_budget_info helpers"
```

---

### Task 3: POST `/api/payment-days`

**Files:**
- Modify: `app.py` (после раздела API `/api/stats-data`)
- Test: `tests/test_daily_budget.py` (добавить тесты эндпоинта)

- [ ] **Шаг 1: Дописать тесты для эндпоинта**

Добавить в конец `tests/test_daily_budget.py`:

```python
def _register_and_login(client):
    client.post('/register', data={
        'username': 'testuser',
        'email': 'test@example.com',
        'password': 'secret123',
        'confirm': 'secret123',
    })
    client.post('/login', data={'username': 'testuser', 'password': 'secret123'})


def test_payment_days_save(client):
    """POST /api/payment-days сохраняет дни выплат."""
    _register_and_login(client)
    resp = client.post('/api/payment-days', data={'salary_day': '25', 'advance_day': '10'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True

    from app import flask_app, db, User
    with flask_app.app_context():
        user = User.query.filter_by(username='testuser').first()
        assert user.salary_day == 25
        assert user.advance_day == 10


def test_payment_days_invalid(client):
    """Значения вне диапазона 1-31 отклоняются."""
    _register_and_login(client)
    resp = client.post('/api/payment-days', data={'salary_day': '99', 'advance_day': '0'})
    assert resp.status_code == 400


def test_payment_days_partial(client):
    """Можно передать только одно поле."""
    _register_and_login(client)
    resp = client.post('/api/payment-days', data={'salary_day': '25'})
    assert resp.status_code == 200
    from app import flask_app, User
    with flask_app.app_context():
        user = User.query.filter_by(username='testuser').first()
        assert user.salary_day == 25
        assert user.advance_day is None


def test_payment_days_requires_login(client):
    """Без авторизации — редирект на /login."""
    resp = client.post('/api/payment-days', data={'salary_day': '25'})
    assert resp.status_code in (302, 401)
```

- [ ] **Шаг 2: Запустить тесты — убедиться, что падают**

```bash
python3 -m pytest tests/test_daily_budget.py::test_payment_days_save -v
```

Ожидаем: `404` (эндпоинт не существует).

- [ ] **Шаг 3: Реализовать эндпоинт в `app.py`**

Добавить после маршрута `/api/stats-data` (перед блоком `with app.app_context()`):

```python
@app.route('/api/payment-days', methods=['POST'])
@login_required
def api_payment_days():
    def parse_day(val):
        if val is None or val == '':
            return None
        try:
            d = int(val)
        except (ValueError, TypeError):
            return -1
        return d if 1 <= d <= 31 else -1

    salary_day  = parse_day(request.form.get('salary_day'))
    advance_day = parse_day(request.form.get('advance_day'))

    if salary_day == -1 or advance_day == -1:
        return jsonify({'error': 'Значение должно быть от 1 до 31'}), 400

    current_user.salary_day  = salary_day
    current_user.advance_day = advance_day
    db.session.commit()
    return jsonify({'ok': True})
```

- [ ] **Шаг 4: Запустить все тесты эндпоинта**

```bash
python3 -m pytest tests/test_daily_budget.py -v
```

Ожидаем: все тесты `PASSED`.

- [ ] **Шаг 5: Коммит**

```bash
git add app.py tests/test_daily_budget.py
git commit -m "feat: add POST /api/payment-days endpoint"
```

---

### Task 4: Передать данные в шаблон index

**Files:**
- Modify: `app.py:538-564` (функция `index`)

- [ ] **Шаг 1: Обновить функцию `index`**

Заменить тело функции `index` (от `uid = current_user.id` до конца `return render_template(...)`):

```python
uid          = current_user.id
summary      = get_monthly_summary(uid, year, month)
budget_map   = get_budget_map(uid, year, month)
total_spent  = sum(float(r.total) for r in summary)
total_income = get_monthly_income(uid, year, month)
balance      = total_income - total_spent

daily_info = get_daily_budget_info(
    balance=balance,
    salary_day=current_user.salary_day,
    advance_day=current_user.advance_day,
)

recent = (
    Expense.query
    .filter(
        Expense.user_id == uid,
        extract('year',  Expense.expense_date) == year,
        extract('month', Expense.expense_date) == month,
    )
    .order_by(Expense.expense_date.desc(), Expense.created_at.desc())
    .limit(5).all()
)

return render_template('index.html',
    summary=summary, budget_map=budget_map,
    total_spent=total_spent, total_income=total_income, balance=balance,
    recent=recent, year=year, month=month, today=today, months=months_list(),
    daily_info=daily_info,
    salary_day=current_user.salary_day,
    advance_day=current_user.advance_day,
)
```

- [ ] **Шаг 2: Запустить приложение и проверить, что главная открывается**

```bash
python3 app.py &
sleep 2
curl -s http://localhost:5000/ -L | grep -c "Трекер"
kill %1
```

Ожидаем: число > 0 (страница отдаётся).

- [ ] **Шаг 3: Коммит**

```bash
git add app.py
git commit -m "feat: pass daily_info to index template"
```

---

### Task 5: Карточка и модалка в шаблоне

**Files:**
- Modify: `templates/index.html:25-87` (блок карточек)
- Modify: `templates/index.html` (конец `{% block content %}` + `{% block scripts %}`)

- [ ] **Шаг 1: Изменить сетку карточек с `col-md-4` на `col-md-3`**

В блоке `<!-- Итоговые карточки -->` (строки 25–87) найти три вхождения `col-md-4` и заменить все три на `col-md-3`:

```html
<!-- было: class="col-md-4" -->
<!-- стало: class="col-md-3" -->
```

Замените в трёх карточках (Доходы, Расходы, Баланс): `class="col-md-4"` → `class="col-md-3"`.

- [ ] **Шаг 2: Добавить четвёртую карточку**

После закрывающего `</div>` карточки «Баланс» (строка ~86), перед закрывающим `</div>` блока `.row` добавить:

```html
    <div class="col-md-3">
        <div class="card summary-card h-100 float-card
            {% if daily_info %}
                {% if daily_info.daily >= 0 %}grad-balance{% else %}grad-danger{% endif %}
            {% else %}grad-secondary{% endif %}"
             id="dailyBudgetCard"
             role="button" tabindex="0"
             aria-label="Настроить даты выплат"
             style="cursor:pointer">
            <div class="card-body d-flex justify-content-between align-items-center">
                <div>
                    <div class="small opacity-75">Можно тратить в день</div>
                    {% if daily_info %}
                        <div class="fs-3 fw-bold count-up"
                             data-value="{{ daily_info.daily }}"
                             data-decimals="2"
                             data-suffix=" ₽">{{ "%.2f"|format(daily_info.daily) }} ₽</div>
                    {% else %}
                        <div class="fs-5 fw-bold">Укажите даты</div>
                    {% endif %}
                </div>
                <i class="bi bi-calendar-check" style="font-size:2.5rem;opacity:.35"></i>
            </div>
            <div class="card-footer pb-2">
                <span class="small text-white-50">
                    {% if daily_info %}
                        до {{ daily_info.payment_type }} {{ daily_info.days_left }} дн.
                    {% else %}
                        нажмите, чтобы настроить
                    {% endif %}
                </span>
            </div>
        </div>
    </div>
```

- [ ] **Шаг 3: Добавить модалку**

Перед `{% endblock %}` (конец `{% block content %}`), добавить:

```html
<!-- Модалка настройки дат выплат -->
<div class="modal fade" id="paymentDaysModal" tabindex="-1" aria-labelledby="paymentDaysModalLabel" aria-hidden="true">
    <div class="modal-dialog modal-sm">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title" id="paymentDaysModalLabel">
                    <i class="bi bi-calendar-check text-primary me-2"></i>Даты выплат
                </h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
                <div class="mb-3">
                    <label class="form-label small fw-semibold">День аванса (1–31)</label>
                    <input type="number" id="advanceDayInput" class="form-control"
                           min="1" max="31" placeholder="не задан"
                           value="{{ advance_day or '' }}">
                </div>
                <div class="mb-3">
                    <label class="form-label small fw-semibold">День зарплаты (1–31)</label>
                    <input type="number" id="salaryDayInput" class="form-control"
                           min="1" max="31" placeholder="не задан"
                           value="{{ salary_day or '' }}">
                </div>
                <div id="paymentDaysError" class="text-danger small d-none"></div>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary btn-sm" data-bs-dismiss="modal">Отмена</button>
                <button type="button" class="btn grad-primary btn-sm" id="savePaymentDays">Сохранить</button>
            </div>
        </div>
    </div>
</div>
```

- [ ] **Шаг 4: Добавить JS в `{% block scripts %}`**

В `{% block scripts %}`, после существующих скриптов, перед закрывающим `</script>`, добавить:

```javascript
// ── Карточка «Можно тратить в день» ──────────────────────────────
(function () {
    const card  = document.getElementById('dailyBudgetCard');
    const modal = new bootstrap.Modal(document.getElementById('paymentDaysModal'));

    card.addEventListener('click', () => modal.show());
    card.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); modal.show(); }
    });

    document.getElementById('savePaymentDays').addEventListener('click', () => {
        const salaryDay  = document.getElementById('salaryDayInput').value.trim();
        const advanceDay = document.getElementById('advanceDayInput').value.trim();
        const errEl      = document.getElementById('paymentDaysError');
        errEl.classList.add('d-none');

        const body = new FormData();
        if (salaryDay)  body.append('salary_day',  salaryDay);
        if (advanceDay) body.append('advance_day', advanceDay);

        fetch('/api/payment-days', { method: 'POST', body })
            .then(r => r.json())
            .then(data => {
                if (data.ok) {
                    window.location.reload();
                } else {
                    errEl.textContent = data.error || 'Ошибка сохранения';
                    errEl.classList.remove('d-none');
                }
            })
            .catch(() => {
                errEl.textContent = 'Ошибка сети';
                errEl.classList.remove('d-none');
            });
    });
})();
```

- [ ] **Шаг 5: Запустить приложение и проверить UI**

```bash
python3 app.py
```

Открыть `http://localhost:5000/` в браузере. Проверить:
- Четыре карточки отображаются в одной строке
- Карточка «Можно тратить в день» показывает «Укажите даты» (если даты не заданы)
- Клик открывает модалку
- После ввода дней и сохранения — страница перезагружается и показывает сумму

- [ ] **Шаг 6: Коммит**

```bash
git add templates/index.html
git commit -m "feat: add daily budget card and payment days modal to index"
```

---

### Task 6: Финальная проверка

- [ ] **Шаг 1: Запустить все тесты**

```bash
python3 -m pytest tests/ -v
```

Ожидаем: все тесты `PASSED`.

- [ ] **Шаг 2: Проверить граничные случаи вручную**

1. Ввести только день зарплаты (без аванса) → карточка показывает корректную сумму
2. Ввести отрицательный баланс (расходы > доходов) → карточка красная с минусом
3. Ввести день 31 в феврале → приложение не падает

- [ ] **Шаг 3: Финальный коммит**

```bash
git add -u
git commit -m "feat: daily budget card — complete implementation"
```
