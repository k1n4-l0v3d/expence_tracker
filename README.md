# Expense Tracker

Веб-приложение для учёта доходов и расходов. Flask + PostgreSQL.

## Функции
- Регистрация и авторизация пользователей
- Учёт расходов по категориям
- Учёт доходов
- Месячный бюджет по категориям
- Панель администратора

## Локальный запуск

1. Клонируй репозиторий:
   ```bash
   git clone https://github.com/ТВО_ИМЯ/expense_tracker.git
   cd expense_tracker
   ```

2. Создай виртуальное окружение:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # macOS/Linux
   ```

3. Установи зависимости:
   ```bash
   pip install -r requirements.txt
   ```

4. Создай `.env` из примера:
   ```bash
   cp .env.example .env
   # Отредактируй .env — вставь свои данные PostgreSQL
   ```

5. Запусти:
   ```bash
   python app.py
   ```

Приложение будет доступно на http://localhost:5000

## Деплой на Railway

Смотри инструкцию в DEPLOY.md
# expence_tracker
