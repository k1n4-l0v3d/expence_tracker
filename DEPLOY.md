# Инструкция: GitHub + Railway

## Шаг 1 — Создать репозиторий на GitHub

1. Зайди на https://github.com и нажми **New repository**
2. Название: `expense_tracker`
3. Тип: **Private** (рекомендуется)
4. Нажми **Create repository**

## Шаг 2 — Залить проект на GitHub

Открой терминал в папке проекта (там, где лежит app.py):

```bash
# Инициализируй git
git init

# Добавь все файлы (кроме тех, что в .gitignore)
git add .

# Первый коммит
git commit -m "Initial commit"

# Добавь ссылку на GitHub (замени YOUR_USERNAME на своё имя)
git remote add origin https://github.com/YOUR_USERNAME/expense_tracker.git

# Залей
git branch -M main
git push -u origin main
```

Проверь что `.env` НЕ попал в GitHub (он в .gitignore).

---

## Шаг 3 — Деплой на Railway

### 3.1 Создать проект

1. Зайди на https://railway.app и авторизуйся через GitHub
2. Нажми **New Project → Deploy from GitHub repo**
3. Выбери репозиторий `expense_tracker`
4. Railway начнёт сборку — подожди

### 3.2 Добавить PostgreSQL

1. В проекте нажми **+ New → Database → Add PostgreSQL**
2. Railway создаст базу и автоматически добавит переменную `DATABASE_URL`

### 3.3 Настроить переменные окружения

1. Кликни на сервис (не базу), перейди в **Variables**
2. Добавь переменную:
   - `SECRET_KEY` = придумай длинную случайную строку, например: `mySuperSecretKey2024xYzAbC`
3. Переменная `DATABASE_URL` уже должна быть добавлена автоматически из PostgreSQL

### 3.4 Проверить деплой

1. Перейди в **Deployments** и дождись статуса **Success**
2. Нажми **Settings → Domains → Generate Domain**
3. Railway даст тебе ссылку вида `expense-tracker-xxx.up.railway.app`
4. Открой — приложение работает!

### 3.5 Первый вход

- Зарегистрируйся по ссылке `/register`
- **Первый зарегистрированный пользователь автоматически становится администратором**

---

## Обновление после изменений

Когда изменишь код локально:

```bash
git add .
git commit -m "Описание изменений"
git push
```

Railway автоматически задеплоит новую версию.
