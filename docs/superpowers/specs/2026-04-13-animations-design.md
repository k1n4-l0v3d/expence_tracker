# Дизайн и анимации — Трекер расходов

**Дата:** 2026-04-13  
**Статус:** Approved  

---

## Обзор

Редизайн и добавление анимаций к Flask-приложению «Трекер расходов». Стиль — **Colorful & Playful** (как Revolut/Monzo). Уровень анимаций — **Cinematic**. Реализация через два новых файла: `static/css/animations.css` и `static/js/animations.js`, подключённых в `templates/base.html`.

---

## Цветовая палитра

### Акцентные градиенты

| Назначение        | Цвет от    | Цвет до    | Использование                        |
|-------------------|------------|------------|--------------------------------------|
| Primary (расходы) | `#e8736b`  | `#f0956a`  | Navbar, кнопки, бейдж расходов       |
| Income Green      | `#3dbb6e`  | `#34c4a8`  | Карточка доходов, прогресс-бары OK   |
| Balance Blue      | `#4a9fd4`  | `#2ec4c4`  | Карточка баланса                     |
| Danger            | `#c0527a`  | `#e06060`  | Перерасход бюджета, ban-статус       |

### Нейтральные

| Токен        | Light mode  | Dark mode   |
|--------------|-------------|-------------|
| Page BG      | `#fdf4ef`   | `#13120f`   |
| Card BG      | `#ffffff`   | `#272220`   |
| Border       | `#f0d9cc`   | `#3a3230`   |
| Text Primary | `#1a1a1a`   | `#f5f0ed`   |
| Text Muted   | `#6b7280`   | `#9a8e88`   |

---

## Архитектура (Подход B)

```
static/
  css/
    style.css          ← существующий, минимальные правки (фон, border-color)
    animations.css     ← новый: все @keyframes, классы входа, hover, градиенты
  js/
    animations.js      ← новый: IntersectionObserver, countUp, skeleton, pulseBtn
templates/
  base.html            ← подключить оба файла
  auth/login.html      ← анимированный фон (без base.html)
  auth/register.html   ← то же
```

`animations.css` не импортирует и не переопределяет Bootstrap — только дополняет.

---

## Анимации — полный список

### @keyframes (в animations.css)

| Имя           | Описание                                    |
|---------------|---------------------------------------------|
| `floatY`      | Покачивание вверх-вниз, 3s loop             |
| `staggerIn`   | Влёт слева + появление, используется с delay |
| `progFill`    | Заполнение прогресс-бара от 0 до `--w`      |
| `pulseRing`   | Пульсирующая тень вокруг кнопки             |
| `shimmer`     | Бегущий блик (skeleton-загрузка)            |
| `shakeX`      | Горизонтальная тряска (ошибка формы)        |
| `successPop`  | Scale 0→1.15→1 с bounce (успех)             |
| `bgMove`      | Плавное движение градиентного фона          |
| `iconBounce`  | Подпрыгивание иконки навигации              |
| `pageIn`      | Появление страницы (opacity + translateY)   |

### CSS-классы

| Класс               | Эффект                                               |
|---------------------|------------------------------------------------------|
| `.float-card`       | `floatY` 3s infinite, разные `animation-delay`       |
| `.stagger-item`     | `staggerIn`, delay задаётся через `--i` (JS)         |
| `.skeleton`         | `shimmer` 1.6s infinite                              |
| `.shake`            | `shakeX` 0.4s, добавляется JS при ошибке формы       |
| `.success-pop`      | `successPop` 0.5s cubic-bezier bounce                |
| `.grad-primary`     | `background: linear-gradient(135deg, #e8736b, #f0956a)` |
| `.grad-income`      | `background: linear-gradient(135deg, #3dbb6e, #34c4a8)` |
| `.grad-balance`     | `background: linear-gradient(135deg, #4a9fd4, #2ec4c4)` |
| `.grad-danger`      | `background: linear-gradient(135deg, #c0527a, #e06060)` |
| `.hover-lift`       | `transform: translateY(-3px)` + shadow on hover      |
| `.prog-bar-animated`| Использует `progFill` + CSS-переменную `--w`         |

### animations.js — логика

| Функция / Observer         | Что делает                                                      |
|----------------------------|-----------------------------------------------------------------|
| `initStagger()`            | IntersectionObserver на `.stagger-item`, добавляет `--i` и класс |
| `initCountUp()`            | Анимирует числа в `.count-up` от 0 до финального значения       |
| `initProgressBars()`       | Устанавливает `--w` из `data-value`, запускает `progFill`       |
| `initPulseButton()`        | Убирает `pulseRing` после первого клика на `.pulse-btn`         |
| `initFormShake()`          | Слушает `submit` форм, добавляет `.shake` при flash-ошибке      |
| `initNavBounce()`          | Добавляет `iconBounce` на активную иконку `.bottom-nav a`       |
| `initSkeleton()`           | Показывает `.skeleton` до загрузки данных Chart.js              |

Все функции вызываются через `DOMContentLoaded`. Каждая проверяет наличие нужных элементов перед запуском.

---

## Изменения по страницам

### base.html
- Подключить `animations.css` и `animations.js`
- Navbar: заменить `bg-primary` на `.grad-primary` + скруглённые края `border-radius: 0 0 16px 16px`
- Карточки суммарника: добавить класс `.float-card` с `animation-delay: 0s / 0.3s / 0.6s`
- Нижняя навигация: кнопка «+» получает `.grad-primary` + `border-radius: 16px` + тень
- Flash-алерты: добавить `staggerIn` при появлении

### auth/login.html и register.html
- `<body>`: фон заменить на анимированный `bgMove` градиент
- Карточка формы: `background: rgba(255,255,255,.92)` + `backdrop-filter: blur(12px)`
- Иконка приложения: заменить текстовый логотип на градиентный квадрат с иконкой
- Поля ввода: `background: #fdf4ef`, focus — цветная `box-shadow`
- Кнопка submit: `.grad-primary` + `.pulse-btn`

### templates/index.html (Dashboard)
- Три карточки: `.float-card` + соответствующий градиент (`.grad-income`, `.grad-primary`, `.grad-balance`)
- Числа в карточках: `.count-up` + `data-value`
- Список «последние расходы»: каждый `<li>` → `.stagger-item`
- Canvas диаграммы: `.skeleton` до загрузки; после — убрать skeleton
- Chart.js: обновить цвета под палитру, добавить кастомный tooltip

### templates/expenses/list.html
- Каждый `.record-card` → `.stagger-item`
- Бейджи категорий: динамический цвет фона из `exp.category.color` → оставить, но добавить `border-radius: 20px`
- Кнопка «Добавить» (десктоп): `.grad-primary`
- Итоговая строка: выделить жирным с цветом `.grad-primary`

### templates/income/list.html
- Аналогично expenses/list.html — stagger-items, кнопка с градиентом

### templates/expenses/form.html и income/form.html
- Поля: focus-glow через CSS (`box-shadow` на `:focus`)
- Кнопка submit: `.grad-primary` + `.pulse-btn`
- При ошибке (flash `danger`): добавить `.shake` на форму через `animations.js`
- При успехе: показать `.success-pop` иконку (JS вставляет перед редиректом)

### templates/budget.html
- Прогресс-бары: заменить Bootstrap `.progress-bar` на `.prog-bar-animated` с `data-value`
- Цвет бара: зелёный (< 70%), оранжевый (70–99%), красный (≥ 100%)
- `animations.js` → `initProgressBars()` запускается при загрузке

### templates/profile.html
- Статистические числа: `.count-up`
- Карточки статистики: `.hover-lift`

### templates/admin/panel.html
- Без анимаций — функциональная страница, излишняя анимация неуместна

---

## Тёмная тема

Существующий механизм `data-bs-theme` сохраняется. В `animations.css`:

```css
[data-bs-theme="dark"] {
  --page-bg: #13120f;
  --card-bg: #272220;
  --border-color: #3a3230;
}
```

Градиентные акценты остаются теми же — они достаточно яркие для обеих тем.

---

## Что НЕ меняется

- Логика Flask (`app.py`) — без изменений
- Структура маршрутов — без изменений
- Bootstrap 5 как основа — сохраняется
- Страница `/admin` — без анимаций (функциональная)
- `schema.sql`, `requirements.txt`, `Procfile` — без изменений

---

## Файлы для создания / изменения

| Файл                              | Действие  |
|-----------------------------------|-----------|
| `static/css/animations.css`       | Создать   |
| `static/js/animations.js`         | Создать   |
| `templates/base.html`             | Изменить  |
| `templates/auth/login.html`       | Изменить  |
| `templates/auth/register.html`    | Изменить  |
| `templates/index.html`            | Изменить  |
| `templates/expenses/list.html`    | Изменить  |
| `templates/expenses/form.html`    | Изменить  |
| `templates/income/list.html`      | Изменить  |
| `templates/income/form.html`      | Изменить  |
| `templates/budget.html`           | Изменить  |
| `templates/profile.html`          | Изменить  |
| `static/css/style.css`            | Изменить (фон страницы, border-color) |
