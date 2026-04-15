# Animations & Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Редизайн Flask-трекера расходов в стиле Colorful & Playful с Cinematic-анимациями через два новых файла — `animations.css` и `animations.js`.

**Architecture:** Подход B — создаём `static/css/animations.css` (все @keyframes и CSS-классы) и `static/js/animations.js` (IntersectionObserver, countUp, progressBars, shake, navBounce). Оба файла подключаются в `base.html`. Существующий `style.css` получает минимальные правки (фон, border-color). Flask-бэкенд не трогаем.

**Tech Stack:** Flask + Jinja2, Bootstrap 5.3.2, Bootstrap Icons 1.11.3, Chart.js 4.4.1, vanilla CSS/JS (без новых зависимостей).

---

## Запуск приложения для проверки

```bash
cd /Users/k1n4_l0v3d/Downloads/expense_tracker_ready
pip install -r requirements.txt
flask run --debug
# Открыть http://127.0.0.1:5000
```

> Если БД не создана — создастся автоматически при первом запуске (`db.create_all()` в `app.py:634`). Зарегистрируй нового пользователя — первый становится admin.

---

## Task 1: Создать `static/css/animations.css`

**Files:**
- Create: `static/css/animations.css`

- [ ] **Step 1: Создать файл с @keyframes и CSS-классами**

```css
/* ══════════════════════════════════════════
   KEYFRAMES
══════════════════════════════════════════ */

@keyframes floatY {
    0%, 100% { transform: translateY(0); }
    50%       { transform: translateY(-7px); }
}

@keyframes staggerIn {
    from { opacity: 0; transform: translateX(-16px); }
    to   { opacity: 1; transform: translateX(0); }
}

@keyframes progFill {
    from { width: 0; }
    to   { width: var(--w, 0%); }
}

@keyframes pulseRing {
    0%   { box-shadow: 0 0 0 0 rgba(232, 115, 107, 0.45); }
    70%  { box-shadow: 0 0 0 10px rgba(232, 115, 107, 0); }
    100% { box-shadow: 0 0 0 0 rgba(232, 115, 107, 0); }
}

@keyframes shimmer {
    0%   { background-position: -300% 0; }
    100% { background-position:  300% 0; }
}

@keyframes shakeX {
    0%, 100%     { transform: translateX(0); }
    20%, 60%     { transform: translateX(-6px); }
    40%, 80%     { transform: translateX(6px); }
}

@keyframes successPop {
    0%   { transform: scale(0);    opacity: 0; }
    60%  { transform: scale(1.15); }
    100% { transform: scale(1);    opacity: 1; }
}

@keyframes bgMove {
    0%   { background-position: 0% 50%; }
    50%  { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}

@keyframes iconBounce {
    0%, 100% { transform: scale(1); }
    30%      { transform: scale(1.35); }
    60%      { transform: scale(0.88); }
}

@keyframes cardPopIn {
    0%   { opacity: 0; transform: translateY(18px) scale(0.96); }
    60%  { transform: translateY(-3px) scale(1.01); }
    100% { opacity: 1; transform: translateY(0) scale(1); }
}

/* ══════════════════════════════════════════
   ЦВЕТОВЫЕ ТОКЕНЫ
══════════════════════════════════════════ */

:root {
    --clr-primary-from: #e8736b;
    --clr-primary-to:   #f0956a;
    --clr-income-from:  #3dbb6e;
    --clr-income-to:    #34c4a8;
    --clr-balance-from: #4a9fd4;
    --clr-balance-to:   #2ec4c4;
    --clr-danger-from:  #c0527a;
    --clr-danger-to:    #e06060;
    --page-bg:          #fdf4ef;
    --card-bg:          #ffffff;
    --border-clr:       #f0d9cc;
}

[data-bs-theme="dark"] {
    --page-bg:    #13120f;
    --card-bg:    #272220;
    --border-clr: #3a3230;
}

/* ══════════════════════════════════════════
   ГРАДИЕНТНЫЕ КЛАССЫ
══════════════════════════════════════════ */

.grad-primary {
    background: linear-gradient(135deg, var(--clr-primary-from), var(--clr-primary-to)) !important;
    color: #fff !important;
    border: none !important;
}

.grad-income {
    background: linear-gradient(135deg, var(--clr-income-from), var(--clr-income-to)) !important;
    color: #fff !important;
    border: none !important;
}

.grad-balance {
    background: linear-gradient(135deg, var(--clr-balance-from), var(--clr-balance-to)) !important;
    color: #fff !important;
    border: none !important;
}

.grad-danger {
    background: linear-gradient(135deg, var(--clr-danger-from), var(--clr-danger-to)) !important;
    color: #fff !important;
    border: none !important;
}

/* ══════════════════════════════════════════
   АНИМАЦИОННЫЕ КЛАССЫ
══════════════════════════════════════════ */

/* Плавающая карточка */
.float-card {
    animation: floatY 3s ease-in-out infinite;
}
.float-card:nth-child(2) { animation-delay: 0.4s; }
.float-card:nth-child(3) { animation-delay: 0.8s; }

/* Stagger — применяется через JS (добавляет .stagger-visible) */
.stagger-item {
    opacity: 0;
}
.stagger-item.stagger-visible {
    animation: staggerIn 0.4s ease both;
    animation-delay: calc(var(--i, 0) * 80ms);
    opacity: 1;
}

/* Skeleton shimmer */
.skeleton {
    background: linear-gradient(
        90deg,
        var(--card-bg) 25%,
        color-mix(in srgb, var(--clr-primary-from) 12%, var(--card-bg)) 50%,
        var(--card-bg) 75%
    );
    background-size: 300% 100%;
    animation: shimmer 1.6s infinite;
    border-radius: 8px;
}

/* Пульсирующая кнопка */
.pulse-btn {
    animation: pulseRing 2s infinite;
}
.pulse-btn.pulse-stopped {
    animation: none;
}

/* Shake при ошибке формы */
.shake {
    animation: shakeX 0.4s ease;
}

/* Успешный pop */
.success-pop {
    animation: successPop 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}

/* Hover-подъём карточки */
.hover-lift {
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    cursor: pointer;
}
.hover-lift:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 24px rgba(232, 115, 107, 0.18) !important;
}

/* Появление карточки при загрузке */
.card-pop-in {
    animation: cardPopIn 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}

/* ══════════════════════════════════════════
   ПРОГРЕСС-БАР
══════════════════════════════════════════ */

.prog-bar-animated {
    height: 100%;
    border-radius: 6px;
    width: 0;
    transition: background 0.3s ease;
}
.prog-bar-animated.prog-ok      { background: linear-gradient(90deg, var(--clr-income-from), var(--clr-income-to)); }
.prog-bar-animated.prog-warning { background: linear-gradient(90deg, var(--clr-primary-to), var(--clr-primary-from)); }
.prog-bar-animated.prog-danger  { background: linear-gradient(90deg, var(--clr-danger-from), var(--clr-danger-to)); }

/* ══════════════════════════════════════════
   НАВБАР
══════════════════════════════════════════ */

.navbar-animated {
    background: linear-gradient(135deg, var(--clr-primary-from), var(--clr-primary-to)) !important;
    border-radius: 0 0 18px 18px;
    box-shadow: 0 4px 20px rgba(232, 115, 107, 0.3);
}

/* ══════════════════════════════════════════
   СТРАНИЦА ВХОДА — фон
══════════════════════════════════════════ */

.auth-bg {
    background: linear-gradient(135deg, #e8736b, #f0956a, #4a9fd4, #3dbb6e);
    background-size: 300% 300%;
    animation: bgMove 10s ease infinite;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
}

.auth-card {
    background: rgba(255, 255, 255, 0.92);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border-radius: 20px;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.15);
    animation: cardPopIn 0.55s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}

[data-bs-theme="dark"] .auth-card {
    background: rgba(39, 34, 32, 0.92);
}

.auth-logo {
    width: 56px;
    height: 56px;
    border-radius: 16px;
    background: linear-gradient(135deg, var(--clr-primary-from), var(--clr-primary-to));
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: #fff;
    font-size: 1.6rem;
    box-shadow: 0 4px 16px rgba(232, 115, 107, 0.4);
    margin-bottom: 12px;
}

/* ══════════════════════════════════════════
   ПОЛЯ ФОРМЫ — focus glow
══════════════════════════════════════════ */

.form-control:focus,
.form-select:focus {
    border-color: var(--clr-primary-from);
    box-shadow: 0 0 0 3px rgba(232, 115, 107, 0.2);
}

/* ══════════════════════════════════════════
   НИЖНЯЯ НАВИГАЦИЯ — кнопка «+»
══════════════════════════════════════════ */

.bottom-nav a.add-btn {
    background: linear-gradient(135deg, var(--clr-primary-from), var(--clr-primary-to)) !important;
    box-shadow: 0 4px 14px rgba(232, 115, 107, 0.45);
    border-radius: 16px !important;
}

/* Иконка активной вкладки */
.bottom-nav a.active i.icon-bounce {
    animation: iconBounce 0.4s ease;
}

/* ══════════════════════════════════════════
   КАРТОЧКИ ДАШБОРДА — цвет текста внутри
══════════════════════════════════════════ */

.summary-card {
    border: none !important;
    border-radius: 16px !important;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.10) !important;
}

.summary-card .card-footer {
    background: transparent !important;
    border: none !important;
}

/* ══════════════════════════════════════════
   RECORD-CARD — hover
══════════════════════════════════════════ */

.record-card {
    transition: box-shadow 0.2s ease, transform 0.2s ease;
}
.record-card:hover {
    box-shadow: 0 4px 16px rgba(232, 115, 107, 0.12);
    transform: translateX(2px);
}
```

- [ ] **Step 2: Убедиться что файл создан**

```bash
ls static/css/
# Ожидание: animations.css  style.css
```

- [ ] **Step 3: Commit**

```bash
git add static/css/animations.css
git commit -m "feat: add animations.css with keyframes and CSS classes"
```

---

## Task 2: Создать `static/js/animations.js`

**Files:**
- Create: `static/js/animations.js`

- [ ] **Step 1: Создать файл**

```bash
mkdir -p static/js
```

- [ ] **Step 2: Написать код**

```javascript
/* animations.js — Cinematic animations for Expense Tracker */

document.addEventListener('DOMContentLoaded', () => {
    initStagger();
    initCountUp();
    initProgressBars();
    initPulseButton();
    initFormShake();
    initNavBounce();
});

/* ── Stagger: элементы влетают при появлении в viewport ── */
function initStagger() {
    const items = document.querySelectorAll('.stagger-item');
    if (!items.length) return;

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (!entry.isIntersecting) return;
            const el = entry.target;
            // Вычислить порядковый номер среди видимых
            const siblings = [...el.parentElement.querySelectorAll('.stagger-item')];
            el.style.setProperty('--i', siblings.indexOf(el));
            el.classList.add('stagger-visible');
            observer.unobserve(el);
        });
    }, { threshold: 0.1 });

    items.forEach(el => observer.observe(el));
}

/* ── CountUp: анимация цифр от 0 до target ── */
function initCountUp() {
    const els = document.querySelectorAll('.count-up');
    if (!els.length) return;

    els.forEach(el => {
        const target = parseFloat(el.dataset.value ?? el.textContent.replace(/[^0-9.]/g, ''));
        if (isNaN(target)) return;

        const duration = 900; // ms
        const start    = performance.now();
        const suffix   = el.dataset.suffix ?? '';
        const decimals = el.dataset.decimals ? parseInt(el.dataset.decimals) : 0;

        function tick(now) {
            const elapsed  = Math.min(now - start, duration);
            const progress = elapsed / duration;
            // easeOutQuart
            const eased    = 1 - Math.pow(1 - progress, 4);
            const current  = target * eased;
            el.textContent = current.toFixed(decimals) + suffix;
            if (elapsed < duration) requestAnimationFrame(tick);
        }

        requestAnimationFrame(tick);
    });
}

/* ── Progress bars: заполнение на основе data-value ── */
function initProgressBars() {
    const bars = document.querySelectorAll('.prog-bar-animated');
    if (!bars.length) return;

    bars.forEach(bar => {
        const pct = parseFloat(bar.dataset.value ?? 0);
        // Цвет по уровню
        if (pct >= 100) {
            bar.classList.add('prog-danger');
        } else if (pct >= 70) {
            bar.classList.add('prog-warning');
        } else {
            bar.classList.add('prog-ok');
        }
        // Запускаем анимацию через rAF чтобы браузер успел отрисовать
        requestAnimationFrame(() => {
            bar.style.setProperty('--w', Math.min(pct, 100) + '%');
            bar.style.animation = 'progFill 1.2s cubic-bezier(0.4, 0, 0.2, 1) forwards';
        });
    });
}

/* ── Pulse button: остановить пульс после первого клика ── */
function initPulseButton() {
    document.querySelectorAll('.pulse-btn').forEach(btn => {
        btn.addEventListener('click', () => btn.classList.add('pulse-stopped'), { once: true });
    });
}

/* ── Form shake: трясти форму если есть flash alert-danger ── */
function initFormShake() {
    const hasDanger = document.querySelector('.alert-danger');
    if (!hasDanger) return;

    const form = document.querySelector('form');
    if (!form) return;

    form.classList.add('shake');
    // Убрать класс после анимации чтобы можно было переиграть
    form.addEventListener('animationend', () => form.classList.remove('shake'), { once: true });
}

/* ── Nav bounce: иконка подпрыгивает при активации вкладки ── */
function initNavBounce() {
    const links = document.querySelectorAll('.bottom-nav a');
    if (!links.length) return;

    links.forEach(link => {
        if (link.classList.contains('active')) {
            const icon = link.querySelector('i');
            if (icon) icon.classList.add('icon-bounce');
        }
    });
}
```

- [ ] **Step 3: Commit**

```bash
git add static/js/animations.js
git commit -m "feat: add animations.js with stagger, countUp, progressBars, shake, navBounce"
```

---

## Task 3: Обновить `static/css/style.css` — фон и border-color

**Files:**
- Modify: `static/css/style.css`

- [ ] **Step 1: Добавить переменные фона страницы в начало файла** (после строки 8, после блока `canvas { transition: none !important; }`)

Найти в файле строку:
```css
/* ── Базовые стили ── */
body {
    font-size: 0.92rem;
}
```

Заменить на:
```css
/* ── Базовые стили ── */
body {
    font-size: 0.92rem;
    background-color: var(--page-bg, #fdf4ef);
}
```

- [ ] **Step 2: Обновить border-color карточек**

Найти:
```css
.card {
    border-radius: 12px;
}
```

Заменить на:
```css
.card {
    border-radius: 12px;
    border-color: var(--border-clr, #f0d9cc);
}
```

- [ ] **Step 3: Commit**

```bash
git add static/css/style.css
git commit -m "feat: update style.css with warm page background and border tokens"
```

---

## Task 4: Обновить `templates/base.html`

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Подключить animations.css в `<head>` — после строки с style.css**

Найти:
```html
    <link href="{{ url_for('static', filename='css/style.css') }}" rel="stylesheet">
```

Заменить на:
```html
    <link href="{{ url_for('static', filename='css/style.css') }}" rel="stylesheet">
    <link href="{{ url_for('static', filename='css/animations.css') }}" rel="stylesheet">
```

- [ ] **Step 2: Подключить animations.js в конец `<body>` — перед закрывающим `</body>`**

Найти (последние строки перед `</body>`):
```html
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
{% block scripts %}{% endblock %}
<script>
```

Заменить на:
```html
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="{{ url_for('static', filename='js/animations.js') }}"></script>
{% block scripts %}{% endblock %}
<script>
```

- [ ] **Step 3: Применить градиент к navbar**

Найти:
```html
<nav class="navbar navbar-dark bg-primary shadow-sm navbar-expand-lg">
```

Заменить на:
```html
<nav class="navbar navbar-dark navbar-animated navbar-expand-lg">
```

- [ ] **Step 4: Обновить кнопку «Добавить» в desktop-navbar**

Найти:
```html
                <li class="nav-item ms-2">
                    <a class="nav-link btn btn-light btn-sm text-primary px-3"
                       href="{{ url_for('expense_add') }}">
                        <i class="bi bi-plus-lg me-1"></i>Добавить
                    </a>
                </li>
```

Заменить на:
```html
                <li class="nav-item ms-2">
                    <a class="nav-link btn btn-sm px-3 text-white pulse-btn"
                       style="background:rgba(255,255,255,.2);border-radius:10px"
                       href="{{ url_for('expense_add') }}">
                        <i class="bi bi-plus-lg me-1"></i>Добавить
                    </a>
                </li>
```

- [ ] **Step 5: Добавить класс stagger-item на flash-алерты**

Найти:
```html
            <div class="alert alert-{{ cat }} alert-dismissible fade show" role="alert">
```

Заменить на:
```html
            <div class="alert alert-{{ cat }} alert-dismissible fade show stagger-item" role="alert">
```

- [ ] **Step 6: Commit**

```bash
git add templates/base.html
git commit -m "feat: apply animated navbar and connect animations files in base.html"
```

---

## Task 5: Редизайн `templates/auth/login.html`

**Files:**
- Modify: `templates/auth/login.html`

- [ ] **Step 1: Заменить весь файл**

```html
<!DOCTYPE html>
<html lang="ru" data-bs-theme="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Вход — Трекер расходов</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
    <link href="{{ url_for('static', filename='css/style.css') }}" rel="stylesheet">
    <link href="{{ url_for('static', filename='css/animations.css') }}" rel="stylesheet">
    <script>
        (function() {
            const t = localStorage.getItem('theme') || 'light';
            document.documentElement.setAttribute('data-bs-theme', t);
        })();
    </script>
</head>
<body>

<div class="auth-bg">
<div style="width:100%;max-width:420px;padding:16px">

    {% with messages = get_flashed_messages(with_categories=true) %}
        {% for cat, msg in messages %}
            <div class="alert alert-{{ cat }} alert-dismissible fade show mb-3 stagger-item">
                {{ msg }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        {% endfor %}
    {% endwith %}

    <div class="auth-card p-4">
        <div class="text-center mb-4">
            <div class="auth-logo mx-auto">
                <i class="bi bi-wallet2"></i>
            </div>
            <h5 class="fw-bold mb-0">Трекер расходов</h5>
            <p class="text-muted small mt-1 mb-0">Войдите в свой аккаунт</p>
        </div>

        <form method="post" id="loginForm">
            <div class="mb-3">
                <label class="form-label fw-semibold">Имя пользователя</label>
                <div class="input-group">
                    <span class="input-group-text"><i class="bi bi-person"></i></span>
                    <input type="text" name="username" class="form-control"
                           placeholder="username" required autofocus>
                </div>
            </div>
            <div class="mb-3">
                <label class="form-label fw-semibold">Пароль</label>
                <div class="input-group">
                    <span class="input-group-text"><i class="bi bi-lock"></i></span>
                    <input type="password" name="password" class="form-control"
                           placeholder="••••••••" required>
                </div>
            </div>
            <div class="mb-4 form-check">
                <input type="checkbox" class="form-check-input" name="remember" id="remember">
                <label class="form-check-label" for="remember">Запомнить меня</label>
            </div>
            <button type="submit" class="btn grad-primary w-100 pulse-btn">
                <i class="bi bi-box-arrow-in-right me-1"></i>Войти
            </button>
        </form>
    </div>

    <p class="text-center mt-3 text-white small">
        Нет аккаунта? <a href="{{ url_for('register') }}" class="text-white fw-bold">Зарегистрироваться</a>
    </p>

</div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
<script src="{{ url_for('static', filename='js/animations.js') }}"></script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add templates/auth/login.html
git commit -m "feat: redesign login page with animated gradient background and glass card"
```

---

## Task 6: Редизайн `templates/auth/register.html`

**Files:**
- Modify: `templates/auth/register.html`

- [ ] **Step 1: Заменить весь файл**

```html
<!DOCTYPE html>
<html lang="ru" data-bs-theme="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Регистрация — Трекер расходов</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
    <link href="{{ url_for('static', filename='css/style.css') }}" rel="stylesheet">
    <link href="{{ url_for('static', filename='css/animations.css') }}" rel="stylesheet">
    <script>
        (function() {
            const t = localStorage.getItem('theme') || 'light';
            document.documentElement.setAttribute('data-bs-theme', t);
        })();
    </script>
</head>
<body>

<div class="auth-bg">
<div style="width:100%;max-width:440px;padding:16px">

    {% with messages = get_flashed_messages(with_categories=true) %}
        {% for cat, msg in messages %}
            <div class="alert alert-{{ cat }} alert-dismissible fade show mb-3 stagger-item">
                {{ msg }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        {% endfor %}
    {% endwith %}

    <div class="auth-card p-4">
        <div class="text-center mb-4">
            <div class="auth-logo mx-auto">
                <i class="bi bi-person-plus"></i>
            </div>
            <h5 class="fw-bold mb-0">Создать аккаунт</h5>
            <p class="text-muted small mt-1 mb-0">Начните отслеживать расходы</p>
        </div>

        <form method="post">
            <div class="mb-3">
                <label class="form-label fw-semibold">Имя пользователя</label>
                <div class="input-group">
                    <span class="input-group-text"><i class="bi bi-person"></i></span>
                    <input type="text" name="username" class="form-control"
                           placeholder="username" required autofocus minlength="3" maxlength="64">
                </div>
            </div>
            <div class="mb-3">
                <label class="form-label fw-semibold">Email</label>
                <div class="input-group">
                    <span class="input-group-text"><i class="bi bi-envelope"></i></span>
                    <input type="email" name="email" class="form-control"
                           placeholder="you@example.com" required>
                </div>
            </div>
            <div class="mb-3">
                <label class="form-label fw-semibold">Пароль</label>
                <div class="input-group">
                    <span class="input-group-text"><i class="bi bi-lock"></i></span>
                    <input type="password" name="password" class="form-control"
                           placeholder="минимум 6 символов" required minlength="6">
                </div>
            </div>
            <div class="mb-4">
                <label class="form-label fw-semibold">Повторите пароль</label>
                <div class="input-group">
                    <span class="input-group-text"><i class="bi bi-lock-fill"></i></span>
                    <input type="password" name="confirm" class="form-control"
                           placeholder="••••••••" required minlength="6">
                </div>
            </div>
            <button type="submit" class="btn grad-primary w-100 pulse-btn">
                <i class="bi bi-person-plus me-1"></i>Зарегистрироваться
            </button>
        </form>
    </div>

    <p class="text-center mt-3 text-white small">
        Уже есть аккаунт? <a href="{{ url_for('login') }}" class="text-white fw-bold">Войти</a>
    </p>

</div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
<script src="{{ url_for('static', filename='js/animations.js') }}"></script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add templates/auth/register.html
git commit -m "feat: redesign register page matching login animated style"
```

---

## Task 7: Обновить `templates/index.html` (Dashboard)

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: Заменить три карточки суммарника (строки 23–72)**

Найти весь блок `<!-- Итоговые карточки -->`:
```html
<!-- Итоговые карточки -->
<div class="row g-3 mb-4">
    <div class="col-md-4">
        <div class="card shadow-sm border-0 bg-success text-white h-100">
```

Заменить весь блок карточек (до закрывающего `</div>` на строке 72) на:
```html
<!-- Итоговые карточки -->
<div class="row g-3 mb-4 summary-cards">
    <div class="col-md-4">
        <div class="card summary-card grad-income h-100 float-card">
            <div class="card-body d-flex justify-content-between align-items-center">
                <div>
                    <div class="small opacity-75">Доходы</div>
                    <div class="fs-3 fw-bold count-up"
                         data-value="{{ total_income }}"
                         data-decimals="2"
                         data-suffix=" ₽">{{ "%.2f"|format(total_income) }} ₽</div>
                </div>
                <i class="bi bi-arrow-down-circle" style="font-size:2.5rem;opacity:.35"></i>
            </div>
            <div class="card-footer pb-2">
                <a href="{{ url_for('income_list', year=year, month=month) }}"
                   class="small text-white-50">все доходы →</a>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card summary-card grad-primary h-100 float-card">
            <div class="card-body d-flex justify-content-between align-items-center">
                <div>
                    <div class="small opacity-75">Расходы</div>
                    <div class="fs-3 fw-bold count-up"
                         data-value="{{ total_spent }}"
                         data-decimals="2"
                         data-suffix=" ₽">{{ "%.2f"|format(total_spent) }} ₽</div>
                </div>
                <i class="bi bi-arrow-up-circle" style="font-size:2.5rem;opacity:.35"></i>
            </div>
            <div class="card-footer pb-2">
                <a href="{{ url_for('expenses_list', year=year, month=month) }}"
                   class="small text-white-50">все расходы →</a>
            </div>
        </div>
    </div>
    <div class="col-md-4">
        <div class="card summary-card h-100 float-card
            {% if balance >= 0 %}grad-balance{% else %}grad-danger{% endif %}">
            <div class="card-body d-flex justify-content-between align-items-center">
                <div>
                    <div class="small opacity-75">Баланс</div>
                    <div class="fs-3 fw-bold count-up"
                         data-value="{{ balance }}"
                         data-decimals="2"
                         data-suffix=" ₽">{{ "%.2f"|format(balance) }} ₽</div>
                </div>
                <i class="bi {% if balance >= 0 %}bi-piggy-bank{% else %}bi-exclamation-triangle{% endif %}"
                   style="font-size:2.5rem;opacity:.35"></i>
            </div>
            <div class="card-footer pb-2">
                <span class="small text-white-50">
                    {% if balance >= 0 %}В запасе{% else %}Перерасход{% endif %}
                </span>
            </div>
        </div>
    </div>
</div>
```

- [ ] **Step 2: Добавить skeleton перед canvas, stagger на список последних расходов, обновить прогресс-бары категорий**

Найти:
```html
            <div class="card-body">
                <canvas id="pieChart" height="230"></canvas>
            </div>
```

Заменить на:
```html
            <div class="card-body position-relative">
                <div id="chartSkeleton" class="skeleton" style="height:230px;border-radius:50%;width:230px;margin:0 auto"></div>
                <canvas id="pieChart" height="230" style="display:none"></canvas>
            </div>
```

Найти в списке последних расходов каждый `<li class="list-group-item px-3 py-2">` и добавить класс `stagger-item`:
```html
                <li class="list-group-item px-3 py-2 stagger-item">
```

Найти блок прогресс-бара категорий (строки с `.progress-bar`):
```html
                        {% if budget > 0 %}
                        {% set pct = [spent / budget * 100, 100]|min %}
                        <div class="progress" style="height:5px">
                            <div class="progress-bar {% if pct > 90 %}bg-danger{% elif pct > 70 %}bg-warning{% else %}bg-success{% endif %}"
                                 style="width:{{ pct }}%"></div>
                        </div>
                        {% endif %}
```

Заменить на:
```html
                        {% if budget > 0 %}
                        {% set pct = [spent / budget * 100, 100]|min %}
                        <div class="progress" style="height:7px;border-radius:6px">
                            <div class="prog-bar-animated"
                                 data-value="{{ pct|round|int }}"></div>
                        </div>
                        {% endif %}
```

- [ ] **Step 3: Обновить Chart.js — скрыть skeleton после загрузки + цвета палитры**

Найти в `{% block scripts %}`:
```javascript
fetch(`/api/chart-data?year={{ year }}&month={{ month }}`)
    .then(r => r.json())
    .then(d => {
        if (!d.data.length) return;
        new Chart(document.getElementById('pieChart'), {
            type: 'doughnut',
            data: { labels: d.labels, datasets: [{ data: d.data, backgroundColor: d.colors, borderWidth: 2 }] },
            options: { plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 12 } } } } }
        });
    });
```

Заменить на:
```javascript
fetch(`/api/chart-data?year={{ year }}&month={{ month }}`)
    .then(r => r.json())
    .then(d => {
        const skeleton = document.getElementById('chartSkeleton');
        const canvas   = document.getElementById('pieChart');
        if (skeleton) skeleton.style.display = 'none';
        if (canvas)   canvas.style.display   = '';
        if (!d.data.length) return;
        new Chart(canvas, {
            type: 'doughnut',
            data: {
                labels: d.labels,
                datasets: [{
                    data: d.data,
                    backgroundColor: d.colors,
                    borderWidth: 3,
                    borderColor: getComputedStyle(document.documentElement)
                                    .getPropertyValue('--card-bg') || '#fff',
                    hoverOffset: 8,
                }]
            },
            options: {
                animation: { animateRotate: true, duration: 900 },
                plugins: {
                    legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 12 }, padding: 16 } },
                    tooltip: {
                        callbacks: {
                            label: ctx => ` ${ctx.label}: ${ctx.parsed.toLocaleString('ru-RU')} ₽`
                        }
                    }
                }
            }
        });
    });
```

- [ ] **Step 4: Commit**

```bash
git add templates/index.html
git commit -m "feat: redesign dashboard with floating cards, countUp, skeleton chart, stagger list"
```

---

## Task 8: Обновить `templates/expenses/list.html`

**Files:**
- Modify: `templates/expenses/list.html`

- [ ] **Step 1: Добавить stagger-item на каждую запись расходов и обновить кнопку**

Найти:
```html
    <a href="{{ url_for('expense_add') }}" class="btn btn-primary btn-sm d-none d-lg-inline-flex">
        <i class="bi bi-plus-lg me-1"></i>Добавить
    </a>
```

Заменить на:
```html
    <a href="{{ url_for('expense_add') }}" class="btn grad-primary btn-sm d-none d-lg-inline-flex pulse-btn">
        <i class="bi bi-plus-lg me-1"></i>Добавить
    </a>
```

Найти:
```html
    <div class="record-card d-flex justify-content-between align-items-start gap-2">
```

Заменить на (добавить `stagger-item`):
```html
    <div class="record-card stagger-item d-flex justify-content-between align-items-start gap-2">
```

- [ ] **Step 2: Commit**

```bash
git add templates/expenses/list.html
git commit -m "feat: add stagger animation and grad button to expenses list"
```

---

## Task 9: Обновить `templates/income/list.html`

**Files:**
- Modify: `templates/income/list.html`

- [ ] **Step 1: Обновить кнопку «Добавить доход» и карточку итога**

Найти:
```html
    <a href="{{ url_for('income_add') }}" class="btn btn-success btn-sm">
        <i class="bi bi-plus-lg me-1"></i>Добавить доход
    </a>
```

Заменить на:
```html
    <a href="{{ url_for('income_add') }}" class="btn grad-income btn-sm pulse-btn">
        <i class="bi bi-plus-lg me-1"></i>Добавить доход
    </a>
```

Найти:
```html
<div class="card shadow-sm border-0 mb-4 bg-success text-white">
```

Заменить на:
```html
<div class="card summary-card grad-income mb-4">
```

- [ ] **Step 2: Добавить stagger-item на записи доходов**

Найти:
```html
    <div class="record-card d-flex justify-content-between align-items-start gap-2">
```

Заменить на:
```html
    <div class="record-card stagger-item d-flex justify-content-between align-items-start gap-2">
```

- [ ] **Step 3: Commit**

```bash
git add templates/income/list.html
git commit -m "feat: add stagger, grad button and styled total card to income list"
```

---

## Task 10: Обновить формы `expenses/form.html` и `income/form.html`

**Files:**
- Modify: `templates/expenses/form.html`
- Modify: `templates/income/form.html`

- [ ] **Step 1: В `expenses/form.html` — обновить кнопку submit**

Найти:
```html
                        <button type="submit" class="btn btn-primary">
                            <i class="bi bi-check-lg me-1"></i>
                            {% if expense %}Сохранить{% else %}Добавить{% endif %}
                        </button>
```

Заменить на:
```html
                        <button type="submit" class="btn grad-primary pulse-btn">
                            <i class="bi bi-check-lg me-1"></i>
                            {% if expense %}Сохранить{% else %}Добавить{% endif %}
                        </button>
```

- [ ] **Step 2: В `income/form.html` — обновить кнопку submit**

Найти:
```html
                        <button type="submit" class="btn btn-success px-4">
                            <i class="bi bi-check-lg me-1"></i>
                            {% if income %}Сохранить{% else %}Добавить{% endif %}
                        </button>
```

Заменить на:
```html
                        <button type="submit" class="btn grad-income px-4 pulse-btn">
                            <i class="bi bi-check-lg me-1"></i>
                            {% if income %}Сохранить{% else %}Добавить{% endif %}
                        </button>
```

- [ ] **Step 3: Commit**

```bash
git add templates/expenses/form.html templates/income/form.html
git commit -m "feat: apply grad buttons and pulse-btn to expense and income forms"
```

---

## Task 11: Обновить `templates/budget.html`

**Files:**
- Modify: `templates/budget.html`

- [ ] **Step 1: Обновить кнопки сохранения**

Найти первую:
```html
                <button class="btn btn-primary btn-sm" type="submit">
                    <i class="bi bi-save me-1"></i>Сохранить
                </button>
```

Заменить на:
```html
                <button class="btn grad-primary btn-sm" type="submit">
                    <i class="bi bi-save me-1"></i>Сохранить
                </button>
```

Найти вторую:
```html
            <div class="mt-4">
                <button class="btn btn-primary" type="submit">
                    <i class="bi bi-save me-1"></i>Сохранить бюджет
                </button>
            </div>
```

Заменить на:
```html
            <div class="mt-4">
                <button class="btn grad-primary pulse-btn" type="submit">
                    <i class="bi bi-save me-1"></i>Сохранить бюджет
                </button>
            </div>
```

> **Примечание:** Реальные прогресс-бары расходов vs. бюджета обновлены в Task 7 (index.html), где уже передаётся `summary` с данными о тратах. Страница `/budget` предназначена для установки лимитов — анимированные бары на ней не нужны.

- [ ] **Step 3: Commit**

```bash
git add templates/budget.html
git commit -m "feat: add grad buttons and animated progress bars to budget page"
```

---

## Task 12: Обновить `templates/profile.html`

**Files:**
- Modify: `templates/profile.html`

- [ ] **Step 1: Добавить count-up к числам статистики и hover-lift к карточкам**

Найти:
```html
                <div class="card shadow-sm border-0 text-center p-3">
                    <div class="fs-2 fw-bold text-danger">{{ "%.0f"|format(total_expenses) }} ₽</div>
```

Заменить на:
```html
                <div class="card shadow-sm border-0 text-center p-3 hover-lift">
                    <div class="fs-2 fw-bold text-danger count-up"
                         data-value="{{ total_expenses }}"
                         data-decimals="0"
                         data-suffix=" ₽">{{ "%.0f"|format(total_expenses) }} ₽</div>
```

Найти:
```html
                <div class="card shadow-sm border-0 text-center p-3">
                    <div class="fs-2 fw-bold text-success">{{ "%.0f"|format(total_income) }} ₽</div>
```

Заменить на:
```html
                <div class="card shadow-sm border-0 text-center p-3 hover-lift">
                    <div class="fs-2 fw-bold text-success count-up"
                         data-value="{{ total_income }}"
                         data-decimals="0"
                         data-suffix=" ₽">{{ "%.0f"|format(total_income) }} ₽</div>
```

- [ ] **Step 2: Обновить аватар профиля с градиентом**

Найти:
```html
                <div class="rounded-circle bg-primary text-white d-inline-flex align-items-center
                            justify-content-center mb-3"
                     style="width:72px;height:72px;font-size:2rem">
```

Заменить на:
```html
                <div class="rounded-circle text-white d-inline-flex align-items-center
                            justify-content-center mb-3 grad-primary card-pop-in"
                     style="width:72px;height:72px;font-size:2rem;box-shadow:0 6px 20px rgba(232,115,107,.35)">
```

- [ ] **Step 3: Обновить кнопку сохранения пароля**

Найти:
```html
                    <button type="submit" class="btn btn-primary">
                        <i class="bi bi-check-lg me-1"></i>Сохранить
                    </button>
```

Заменить на:
```html
                    <button type="submit" class="btn grad-primary">
                        <i class="bi bi-check-lg me-1"></i>Сохранить
                    </button>
```

- [ ] **Step 4: Commit**

```bash
git add templates/profile.html
git commit -m "feat: add count-up stats, hover-lift cards and grad avatar to profile"
```

---

## Финальная проверка

- [ ] **Запустить приложение**

```bash
flask run --debug
```

- [ ] **Проверить страницы по чеклисту:**

| Страница           | Что проверить                                                              |
|--------------------|----------------------------------------------------------------------------|
| `/login`           | Анимированный градиентный фон, стеклянная карточка, пульс-кнопка          |
| `/register`        | То же что login                                                            |
| `/` (dashboard)    | 3 плавающие карточки, цифры считаются, список влетает, skeleton→диаграмма |
| `/expenses`        | Элементы влетают с задержкой, кнопка «Добавить» с градиентом              |
| `/income`          | То же что расходы, зелёная карточка итога                                  |
| `/expenses/add`    | Focus-glow на полях, пульс-кнопка, shake при ошибке                       |
| `/income/add`      | То же что /expenses/add                                                    |
| `/budget`          | Градиентные кнопки, прогресс-бары                                         |
| `/profile`         | Цифры считаются, аватар с градиентом, hover на карточках                  |
| Тёмная тема        | Переключить — фон страницы тёмный, градиенты остаются яркими              |
| Мобильный (<768px) | Нижний nav виден, кнопка «+» с градиентом и тенью                         |

- [ ] **Финальный commit**

```bash
git add -A
git commit -m "feat: complete Colorful & Playful redesign with Cinematic animations"
```
