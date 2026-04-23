# Local Hosting — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow running the Flask app locally with `./run.sh`, accessible on localhost and to other LAN devices.

**Architecture:** Update `app.py`'s `__main__` block to read host/port/debug from env vars; add `run.sh` that loads `.env.local` and starts the app; add `.env.local.example` as a template; update `.gitignore`. Production (Railway + gunicorn) is unaffected.

**Tech Stack:** Flask 3.1, Python 3, bash, existing local PostgreSQL.

---

## Files

- Modify: `app.py` — last 2 lines (the `if __name__ == '__main__':` block)
- Modify: `.gitignore` — add `.env.local`
- Create: `run.sh` — one-command launcher
- Create: `.env.local.example` — template the user copies and fills in

---

### Task 1: Update `app.py` entry point

**Files:**
- Modify: `app.py` — lines at the very bottom (`if __name__ == '__main__':`)

- [ ] **Step 1: Replace the `__main__` block**

Find the last two lines of `app.py`:
```python
if __name__ == '__main__':
    app.run(debug=False)
```

Replace with:
```python
if __name__ == '__main__':
    host  = os.getenv('FLASK_HOST', '127.0.0.1')
    port  = int(os.getenv('FLASK_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host=host, port=port, debug=debug)
```

`os` is already imported at the top of `app.py` — no new import needed.

- [ ] **Step 2: Verify syntax**

```bash
python3 -c "import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: read FLASK_HOST/PORT/DEBUG from env for local hosting"
```

---

### Task 2: Add `.env.local` to `.gitignore`

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add the line**

Open `.gitignore` and add after the `.env` line:
```
.env.local
```

The relevant section should look like:
```
# Переменные окружения (ВАЖНО — не заливать!)
.env
.env.local
```

- [ ] **Step 2: Verify git ignores it**

```bash
echo "test" > .env.local
git check-ignore -v .env.local
```

Expected output: `.gitignore:N:.env.local    .env.local`

Then remove the test file — the real one is created in Task 4:
```bash
rm .env.local
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore .env.local"
```

---

### Task 3: Create `run.sh`

**Files:**
- Create: `run.sh`

- [ ] **Step 1: Create the file**

Create `run.sh` in the project root with this content:

```bash
#!/bin/bash
# Локальный запуск: ./run.sh
# Требует наличия .env.local рядом с app.py

if [ ! -f .env.local ]; then
    echo "Ошибка: файл .env.local не найден."
    echo "Скопируй .env.local.example → .env.local и заполни значения."
    exit 1
fi

set -a
source .env.local
set +a

echo "Запуск на http://${FLASK_HOST:-127.0.0.1}:${FLASK_PORT:-5000}"
python3 app.py
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x run.sh
```

- [ ] **Step 3: Verify it fails gracefully without `.env.local`**

```bash
./run.sh
```

Expected output:
```
Ошибка: файл .env.local не найден.
Скопируй .env.local.example → .env.local и заполни значения.
```

- [ ] **Step 4: Commit**

```bash
git add run.sh
git commit -m "feat: add run.sh for local server launch"
```

---

### Task 4: Create `.env.local.example`

**Files:**
- Create: `.env.local.example`

- [ ] **Step 1: Create the template file**

Create `.env.local.example` in the project root:

```
# Скопируй этот файл в .env.local и заполни своими данными
# cp .env.local.example .env.local

# Подключение к локальному PostgreSQL
# Формат: postgresql://ПОЛЬЗОВАТЕЛЬ:ПАРОЛЬ@localhost:5432/ИМЯ_БД
DATABASE_URL=postgresql://postgres:ПАРОЛЬ@localhost:5432/expense_tracker

# Секретный ключ Flask (любая длинная случайная строка)
SECRET_KEY=замени-на-случайную-строку

# Сетевые настройки
# 0.0.0.0 — доступно всем устройствам в локальной сети
# 127.0.0.1 — только этот компьютер
FLASK_HOST=0.0.0.0
FLASK_PORT=5000

# Режим отладки (true/false)
FLASK_DEBUG=false
```

- [ ] **Step 2: Verify `.env.local.example` is tracked by git (NOT ignored)**

```bash
git check-ignore -v .env.local.example
```

Expected: no output (file is NOT ignored — it's a safe template without real credentials).

- [ ] **Step 3: Commit**

```bash
git add .env.local.example
git commit -m "docs: add .env.local.example template for local hosting"
```

---

### Task 5: First local run

- [ ] **Step 1: Create your `.env.local`**

```bash
cp .env.local.example .env.local
```

Open `.env.local` and fill in:
- `DATABASE_URL` — замени `ПАРОЛЬ` и `expense_tracker` на свои значения
- `SECRET_KEY` — любая строка, например: `my-local-secret-2026`

- [ ] **Step 2: Run the server**

```bash
./run.sh
```

Expected output:
```
Запуск на http://0.0.0.0:5000
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
 * Running on http://192.168.X.X:5000
```

- [ ] **Step 3: Verify localhost access**

Open `http://localhost:5000` in the browser — сайт открывается, можно войти.

- [ ] **Step 4: Verify LAN access**

Find Mac's local IP:
```bash
ipconfig getifaddr en0
```

Open `http://<полученный-IP>:5000` с телефона или другого устройства в той же Wi-Fi сети — сайт открывается.
