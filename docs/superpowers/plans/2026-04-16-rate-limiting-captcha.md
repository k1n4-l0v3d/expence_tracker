# Rate Limiting + Captcha Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Protect `/login` and `/register` from brute force — IP-based rate limiting (10 attempts / 5 min), math captcha, honeypot field.

**Architecture:** `RateLimiter` class and `generate_captcha()` helper added directly to `app.py`. All three checks (honeypot → rate limit → captcha) run at the top of each POST handler before existing auth logic. HTML templates gain captcha input and honeypot field.

**Tech Stack:** Flask, Flask-WTF (already installed), Python stdlib `random`/`threading`/`datetime`, pytest, pytest-flask

---

### Task 1: Test infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Install test dependencies**

```bash
cd /Users/k1n4_l0v3d/expence_tracker.15.04.26
pip3 install pytest pytest-flask
```

Expected: `Successfully installed pytest-... pytest-flask-...`

- [ ] **Step 2: Add to requirements.txt**

Add two lines at the end of `requirements.txt`:
```
pytest==8.3.5
pytest-flask==1.3.0
```

- [ ] **Step 3: Create tests/__init__.py (empty)**

```python
```

- [ ] **Step 4: Create tests/conftest.py**

```python
import os

# Must be set BEFORE importing app — load_dotenv() does not override existing env vars
os.environ["DATABASE_URL"] = "sqlite:///instance/test_expense.db"
os.environ["SECRET_KEY"] = "test-secret-key-for-tests-only"

import pytest
from app import app as flask_app, db, rate_limiter


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Create all tables once per test session, drop and delete file after."""
    flask_app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
    })
    with flask_app.app_context():
        db.create_all()
    yield
    with flask_app.app_context():
        db.drop_all()
    try:
        os.remove("instance/test_expense.db")
    except FileNotFoundError:
        pass


@pytest.fixture(autouse=True)
def clean_db():
    """Delete all rows between tests."""
    yield
    with flask_app.app_context():
        from app import User, Expense, Income, MonthlyBudget
        db.session.query(MonthlyBudget).delete()
        db.session.query(Income).delete()
        db.session.query(Expense).delete()
        db.session.query(User).delete()
        db.session.commit()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear IP counters between tests."""
    rate_limiter._data.clear()
    yield
    rate_limiter._data.clear()


@pytest.fixture
def client():
    return flask_app.test_client()
```

- [ ] **Step 5: Verify test runner works**

```bash
pytest tests/ -v
```

Expected: `no tests ran` or `0 passed` — no errors on collection.

- [ ] **Step 6: Commit**

```bash
git add tests/ requirements.txt
git commit -m "test: add pytest infrastructure"
```

---

### Task 2: RateLimiter class (TDD)

**Files:**
- Create: `tests/test_rate_limiter.py`
- Modify: `app.py` — add `import threading`, `import random` to import block; add `RateLimiter` class and `rate_limiter` instance before `load_dotenv()`

- [ ] **Step 1: Write failing tests**

Create `tests/test_rate_limiter.py`:

```python
from datetime import datetime, timedelta
from app import RateLimiter


def test_not_blocked_initially():
    rl = RateLimiter(max_attempts=3, block_minutes=5)
    blocked, minutes = rl.is_blocked("1.2.3.4")
    assert blocked is False
    assert minutes == 0


def test_not_blocked_below_threshold():
    rl = RateLimiter(max_attempts=3, block_minutes=5)
    rl.record_failure("1.2.3.4")
    rl.record_failure("1.2.3.4")
    blocked, _ = rl.is_blocked("1.2.3.4")
    assert blocked is False


def test_blocked_after_max_attempts():
    rl = RateLimiter(max_attempts=3, block_minutes=5)
    for _ in range(3):
        rl.record_failure("1.2.3.4")
    blocked, minutes = rl.is_blocked("1.2.3.4")
    assert blocked is True
    assert minutes >= 1


def test_different_ips_are_independent():
    rl = RateLimiter(max_attempts=2, block_minutes=5)
    for _ in range(2):
        rl.record_failure("1.1.1.1")
    blocked, _ = rl.is_blocked("2.2.2.2")
    assert blocked is False


def test_reset_clears_block():
    rl = RateLimiter(max_attempts=2, block_minutes=5)
    for _ in range(2):
        rl.record_failure("1.2.3.4")
    rl.reset("1.2.3.4")
    blocked, _ = rl.is_blocked("1.2.3.4")
    assert blocked is False


def test_block_expires_after_time():
    rl = RateLimiter(max_attempts=1, block_minutes=5)
    rl.record_failure("1.2.3.4")
    # Manually expire the block
    rl._data["1.2.3.4"]["blocked_until"] = datetime.utcnow() - timedelta(seconds=1)
    blocked, _ = rl.is_blocked("1.2.3.4")
    assert blocked is False
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_rate_limiter.py -v
```

Expected: `ImportError: cannot import name 'RateLimiter' from 'app'`

- [ ] **Step 3: Add imports to app.py**

In `app.py`, add to the existing import block (after `import os`):

```python
import random
import threading
from datetime import datetime, timedelta
```

- [ ] **Step 4: Add RateLimiter class to app.py**

Add BEFORE `load_dotenv()` in `app.py`:

```python
class RateLimiter:
    def __init__(self, max_attempts: int = 10, block_minutes: int = 5):
        self._data: dict = {}
        self._lock = threading.Lock()
        self.max_attempts = max_attempts
        self.block_minutes = block_minutes

    def is_blocked(self, ip: str) -> tuple:
        """Returns (is_blocked: bool, minutes_remaining: int)."""
        with self._lock:
            entry = self._data.get(ip)
            if not entry:
                return False, 0
            blocked_until = entry.get("blocked_until")
            if blocked_until and datetime.utcnow() < blocked_until:
                remaining = int((blocked_until - datetime.utcnow()).total_seconds() // 60) + 1
                return True, remaining
            return False, 0

    def record_failure(self, ip: str) -> None:
        with self._lock:
            entry = self._data.setdefault(ip, {"count": 0, "blocked_until": None})
            entry["count"] += 1
            if entry["count"] >= self.max_attempts:
                entry["blocked_until"] = datetime.utcnow() + timedelta(minutes=self.block_minutes)

    def reset(self, ip: str) -> None:
        with self._lock:
            self._data.pop(ip, None)


rate_limiter = RateLimiter()
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
pytest tests/test_rate_limiter.py -v
```

Expected: `6 passed`

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_rate_limiter.py
git commit -m "feat: add RateLimiter class with IP-based blocking"
```

---

### Task 3: generate_captcha() and get_client_ip() (TDD)

**Files:**
- Create: `tests/test_captcha.py`
- Modify: `app.py` — add `generate_captcha()` and `get_client_ip()` after `rate_limiter = RateLimiter()`

- [ ] **Step 1: Write failing tests**

Create `tests/test_captcha.py`:

```python
import re
from app import generate_captcha


def test_returns_question_string_and_int_answer():
    question, answer = generate_captcha()
    assert isinstance(question, str)
    assert isinstance(answer, int)


def test_question_matches_expected_format():
    for _ in range(30):
        question, _ = generate_captcha()
        assert re.match(r'^\d+\s*[+\-×]\s*\d+$', question), f"Bad format: {question}"


def test_math_answer_is_correct():
    for _ in range(50):
        question, answer = generate_captcha()
        match = re.match(r'^(\d+)\s*([+\-×])\s*(\d+)$', question)
        assert match, f"Could not parse: {question}"
        a, op, b = int(match.group(1)), match.group(2), int(match.group(3))
        if op == '+':
            assert answer == a + b
        elif op == '-':
            assert answer == a - b
        elif op == '×':
            assert answer == a * b


def test_answer_is_non_negative():
    for _ in range(50):
        _, answer = generate_captcha()
        assert answer >= 0
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_captcha.py -v
```

Expected: `ImportError: cannot import name 'generate_captcha' from 'app'`

- [ ] **Step 3: Add generate_captcha() and get_client_ip() to app.py**

Add AFTER `rate_limiter = RateLimiter()` (still before `load_dotenv()`):

```python
def generate_captcha() -> tuple:
    """Return (question_str, answer_int) for a random arithmetic problem."""
    op = random.choice(['+', '-', '×'])
    if op == '+':
        a, b = random.randint(1, 20), random.randint(1, 20)
        return f"{a} + {b}", a + b
    elif op == '-':
        a = random.randint(2, 20)
        b = random.randint(1, a)
        return f"{a} - {b}", a - b
    else:  # ×
        a, b = random.randint(1, 10), random.randint(1, 10)
        return f"{a} × {b}", a * b


def get_client_ip() -> str:
    """Return real client IP, handling X-Forwarded-For from reverse proxies."""
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or '127.0.0.1'
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_captcha.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_captcha.py
git commit -m "feat: add generate_captcha() and get_client_ip() helpers"
```

---

### Task 4: Update /register route (TDD)

**Files:**
- Create: `tests/test_register.py`
- Modify: `app.py` — replace existing `register()` function

- [ ] **Step 1: Write failing tests**

Create `tests/test_register.py`:

```python
import pytest
from app import flask_app, rate_limiter


VALID_FORM = {
    'username': 'testuser',
    'email': 'test@example.com',
    'password': 'password123',
    'confirm': 'password123',
    'captcha': '5',
    'website': '',
}


@pytest.fixture
def client_with_captcha(client):
    """Client with captcha_answer=5 pre-set in session."""
    with client.session_transaction() as sess:
        sess['captcha_answer'] = 5
    return client


def test_get_register_returns_captcha_question(client):
    response = client.get('/register')
    assert response.status_code == 200
    # Page must show arithmetic operator
    data = response.data.decode()
    assert any(op in data for op in ['+', '−', '×', '-']), "No captcha question found"


def test_honeypot_filled_silently_rejected(client_with_captcha):
    data = {**VALID_FORM, 'website': 'http://spam.com'}
    response = client_with_captcha.post('/register', data=data)
    assert response.status_code == 200
    assert b'\xd0\xa3\xd1\x81\xd0\xbf\xd0\xb5\xd1\x88\xd0\xbd' not in response.data  # "Успешн" not in page


def test_blocked_ip_rejected(client_with_captcha):
    for _ in range(10):
        rate_limiter.record_failure('127.0.0.1')
    response = client_with_captcha.post('/register', data=VALID_FORM)
    assert response.status_code == 200
    assert 'много попыток'.encode() in response.data


def test_wrong_captcha_rejected(client):
    with client.session_transaction() as sess:
        sess['captcha_answer'] = 5
    data = {**VALID_FORM, 'captcha': '99'}
    response = client.post('/register', data=data)
    assert response.status_code == 200
    assert 'капч'.encode() in response.data


def test_password_mismatch_records_failure(client_with_captcha):
    data = {**VALID_FORM, 'confirm': 'different'}
    client_with_captcha.post('/register', data=data)
    assert rate_limiter._data.get('127.0.0.1', {}).get('count', 0) == 1


def test_successful_registration(client_with_captcha):
    response = client_with_captcha.post('/register', data=VALID_FORM, follow_redirects=True)
    assert response.status_code == 200
    assert 'testuser'.encode() in response.data


def test_successful_registration_resets_rate_limiter(client_with_captcha):
    rate_limiter.record_failure('127.0.0.1')
    client_with_captcha.post('/register', data=VALID_FORM, follow_redirects=True)
    assert '127.0.0.1' not in rate_limiter._data
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_register.py -v
```

Expected: most tests fail (honeypot/captcha checks don't exist yet)

- [ ] **Step 3: Replace register() in app.py**

Find and replace the entire `register()` function (currently starts with `@app.route('/register', ...)`):

```python
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'GET':
        question, answer = generate_captcha()
        session['captcha_answer'] = answer
        return render_template('auth/register.html', captcha_question=question)

    # ── POST ──────────────────────────────────────────────────────────
    ip = get_client_ip()

    # 1. Honeypot
    if request.form.get('website', ''):
        question, answer = generate_captcha()
        session['captcha_answer'] = answer
        return render_template('auth/register.html', captcha_question=question)

    # 2. Rate limit
    blocked, minutes = rate_limiter.is_blocked(ip)
    if blocked:
        flash(f'Слишком много попыток. Попробуйте через {minutes} мин.', 'danger')
        question, answer = generate_captcha()
        session['captcha_answer'] = answer
        return render_template('auth/register.html', captcha_question=question)

    # 3. Captcha
    try:
        user_answer = int(request.form.get('captcha', ''))
    except (ValueError, TypeError):
        user_answer = None

    if user_answer != session.get('captcha_answer'):
        flash('Неверный ответ на капчу.', 'danger')
        question, answer = generate_captcha()
        session['captcha_answer'] = answer
        return render_template('auth/register.html', captcha_question=question)

    # 4. Existing validation
    username = request.form['username'].strip()
    email    = request.form['email'].strip().lower()
    password = request.form['password']
    confirm  = request.form['confirm']

    if password != confirm:
        flash('Пароли не совпадают.', 'danger')
        rate_limiter.record_failure(ip)
    elif User.query.filter_by(username=username).first():
        flash('Имя пользователя уже занято.', 'danger')
        rate_limiter.record_failure(ip)
    elif User.query.filter_by(email=email).first():
        flash('Email уже зарегистрирован.', 'danger')
        rate_limiter.record_failure(ip)
    else:
        role = 'admin' if User.query.count() == 0 else 'user'
        user = User(username=username, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        rate_limiter.reset(ip)
        flash(f'Добро пожаловать, {username}!{"  Вы — администратор." if role == "admin" else ""}', 'success')
        return redirect(url_for('index'))

    question, answer = generate_captcha()
    session['captcha_answer'] = answer
    return render_template('auth/register.html', captcha_question=question)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_register.py -v
```

Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_register.py
git commit -m "feat: add honeypot + rate limit + captcha to /register"
```

---

### Task 5: Update /login route (TDD)

**Files:**
- Create: `tests/test_login.py`
- Modify: `app.py` — replace existing `login()` function

- [ ] **Step 1: Write failing tests**

Create `tests/test_login.py`:

```python
import pytest
from app import flask_app, db, rate_limiter
from app import User


@pytest.fixture
def existing_user():
    """Create a test user in the database."""
    with flask_app.app_context():
        u = User(username='alice', email='alice@example.com', role='user')
        u.set_password('secret123')
        db.session.add(u)
        db.session.commit()


@pytest.fixture
def client_with_captcha(client):
    with client.session_transaction() as sess:
        sess['captcha_answer'] = 5
    return client


def test_get_login_returns_captcha_question(client):
    response = client.get('/login')
    assert response.status_code == 200
    data = response.data.decode()
    assert any(op in data for op in ['+', '−', '×', '-']), "No captcha question found"


def test_honeypot_filled_silently_rejected(client_with_captcha):
    response = client_with_captcha.post('/login', data={
        'username': 'alice', 'password': 'secret123',
        'captcha': '5', 'website': 'http://bot.com',
    })
    assert response.status_code == 200
    # No success flash, no redirect
    assert b'alert-success' not in response.data


def test_blocked_ip_rejected(client_with_captcha):
    for _ in range(10):
        rate_limiter.record_failure('127.0.0.1')
    response = client_with_captcha.post('/login', data={
        'username': 'alice', 'password': 'secret123',
        'captcha': '5', 'website': '',
    })
    assert 'много попыток'.encode() in response.data


def test_wrong_captcha_rejected(client):
    with client.session_transaction() as sess:
        sess['captcha_answer'] = 5
    response = client.post('/login', data={
        'username': 'alice', 'password': 'secret123',
        'captcha': '99', 'website': '',
    })
    assert 'капч'.encode() in response.data


def test_wrong_password_records_failure(client_with_captcha, existing_user):
    client_with_captcha.post('/login', data={
        'username': 'alice', 'password': 'wrong',
        'captcha': '5', 'website': '',
    })
    assert rate_limiter._data.get('127.0.0.1', {}).get('count', 0) == 1


def test_successful_login_resets_rate_limiter(client_with_captcha, existing_user):
    rate_limiter.record_failure('127.0.0.1')
    client_with_captcha.post('/login', data={
        'username': 'alice', 'password': 'secret123',
        'captcha': '5', 'website': '',
    }, follow_redirects=True)
    assert '127.0.0.1' not in rate_limiter._data


def test_successful_login_redirects(client_with_captcha, existing_user):
    response = client_with_captcha.post('/login', data={
        'username': 'alice', 'password': 'secret123',
        'captcha': '5', 'website': '',
    })
    assert response.status_code == 302
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_login.py -v
```

Expected: honeypot/captcha/rate-limit tests fail

- [ ] **Step 3: Replace login() in app.py**

Find and replace the entire `login()` function:

```python
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'GET':
        question, answer = generate_captcha()
        session['captcha_answer'] = answer
        return render_template('auth/login.html', captcha_question=question)

    # ── POST ──────────────────────────────────────────────────────────
    ip = get_client_ip()

    # 1. Honeypot
    if request.form.get('website', ''):
        question, answer = generate_captcha()
        session['captcha_answer'] = answer
        return render_template('auth/login.html', captcha_question=question)

    # 2. Rate limit
    blocked, minutes = rate_limiter.is_blocked(ip)
    if blocked:
        flash(f'Слишком много попыток. Попробуйте через {minutes} мин.', 'danger')
        question, answer = generate_captcha()
        session['captcha_answer'] = answer
        return render_template('auth/login.html', captcha_question=question)

    # 3. Captcha
    try:
        user_answer = int(request.form.get('captcha', ''))
    except (ValueError, TypeError):
        user_answer = None

    if user_answer != session.get('captcha_answer'):
        flash('Неверный ответ на капчу.', 'danger')
        question, answer = generate_captcha()
        session['captcha_answer'] = answer
        return render_template('auth/login.html', captcha_question=question)

    # 4. Existing auth logic
    username = request.form['username'].strip()
    password = request.form['password']
    user = User.query.filter_by(username=username).first()

    if user and user.check_password(password):
        if user.is_banned:
            flash(f'Аккаунт заблокирован. Причина: {user.ban_reason or "не указана"}.', 'danger')
            rate_limiter.record_failure(ip)
        else:
            login_user(user, remember=request.form.get('remember') == 'on')
            rate_limiter.reset(ip)
            flash(f'Вы вошли как {user.username}.', 'success')
            next_page = request.args.get('next')
            if next_page and not is_safe_url(next_page):
                next_page = None
            return redirect(next_page or url_for('index'))
    else:
        flash('Неверное имя пользователя или пароль.', 'danger')
        rate_limiter.record_failure(ip)

    question, answer = generate_captcha()
    session['captcha_answer'] = answer
    return render_template('auth/login.html', captcha_question=question)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_login.py -v
```

Expected: `7 passed`

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass (20+)

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_login.py
git commit -m "feat: add honeypot + rate limit + captcha to /login"
```

---

### Task 6: Update HTML templates

**Files:**
- Modify: `templates/auth/login.html`
- Modify: `templates/auth/register.html`

- [ ] **Step 1: Update templates/auth/login.html**

Add inside `<form method="post" id="loginForm">`, AFTER the existing `<input type="hidden" name="csrf_token" ...>` and BEFORE the submit button:

```html
            <!-- Honeypot — hidden from real users, filled by bots -->
            <input type="text" name="website" tabindex="-1" autocomplete="off"
                   style="display:none;position:absolute;left:-9999px" aria-hidden="true">

            <!-- Math captcha -->
            <div class="mb-3">
                <label class="form-label fw-semibold">Сколько будет: {{ captcha_question }}?</label>
                <div class="input-group">
                    <span class="input-group-text"><i class="bi bi-calculator"></i></span>
                    <input type="number" name="captcha" class="form-control"
                           placeholder="Введите ответ" required autocomplete="off">
                </div>
            </div>
```

- [ ] **Step 2: Update templates/auth/register.html**

Add inside `<form method="post">`, AFTER the existing `<input type="hidden" name="csrf_token" ...>` and BEFORE the submit button:

```html
            <!-- Honeypot -->
            <input type="text" name="website" tabindex="-1" autocomplete="off"
                   style="display:none;position:absolute;left:-9999px" aria-hidden="true">

            <!-- Math captcha -->
            <div class="mb-4">
                <label class="form-label fw-semibold">Сколько будет: {{ captcha_question }}?</label>
                <div class="input-group">
                    <span class="input-group-text"><i class="bi bi-calculator"></i></span>
                    <input type="number" name="captcha" class="form-control"
                           placeholder="Введите ответ" required autocomplete="off">
                </div>
            </div>
```

- [ ] **Step 3: Start the app and check login page visually**

```bash
python3 app.py &
```

Open http://127.0.0.1:5000/login — verify captcha question appears (e.g. "Сколько будет: 7 + 4?").
Open http://127.0.0.1:5000/register — verify same.

Kill server: `lsof -ti :5000 | xargs kill -9`

- [ ] **Step 4: Final commit**

```bash
git add templates/auth/login.html templates/auth/register.html
git commit -m "feat: add captcha field and honeypot to login/register forms"
```

---

## Self-review

**Spec coverage:**
- ✅ Rate limiting by IP (10 attempts / 5 min) — Task 2 + Task 4 + Task 5
- ✅ Math captcha — Task 3 + Task 4 + Task 5 + Task 6
- ✅ Honeypot — Task 4 + Task 5 + Task 6
- ✅ Applied to both /login and /register — Task 4 + Task 5
- ✅ Check order: honeypot → rate limit → captcha → auth — both routes

**Placeholder scan:** None found.

**Type consistency:**
- `generate_captcha()` returns `tuple` (str, int) — used consistently as `question, answer = generate_captcha()` in Tasks 3, 4, 5
- `rate_limiter.is_blocked()` returns `tuple` (bool, int) — used as `blocked, minutes = ...` in Tasks 2, 4, 5
- `get_client_ip()` returns `str` — used as `ip = get_client_ip()` in Tasks 4, 5
- `rate_limiter` instance name — consistent throughout
