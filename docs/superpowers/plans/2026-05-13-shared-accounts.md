# Совместные счета — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить SharedAccount + SharedAccountMember модели, переключение контекста в сессии Flask и обновить существующие маршруты расходов/доходов/бюджета/накоплений для работы в личном или общем режиме.

**Architecture:** Два новых класса SQLAlchemy (`SharedAccount`, `SharedAccountMember`); nullable FK `shared_account_id` добавляется в `Expense`, `Income`, `MonthlyBudget`, `SavingsAccount`; хелпер `get_active_context()` читает Flask `session['active_shared_account_id']`; декоратор `shared_member_required` защищает новые маршруты; context processor инжектирует список счетов в шаблоны.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, Bootstrap 5, pytest, SQLite (тесты), PostgreSQL (прод)

---

## File Map

| Файл | Изменение |
|---|---|
| `app.py` | Добавить модели, хелперы, декоратор, 6 новых маршрутов, обновить существующие маршруты и 2 context processor |
| `templates/base.html` | Добавить context switcher в navbar и shared-banner |
| `templates/shared/manage.html` | Создать (страница управления счётом) |
| `tests/conftest.py` | Добавить `SharedAccount`, `SharedAccountMember` в `clean_db` |
| `tests/test_shared_accounts.py` | Создать (все тесты) |

---

## Task 1: Модели SharedAccount и SharedAccountMember

**Files:**
- Modify: `app.py` — добавить модели после класса `Debt` (после строки ~278)
- Modify: `app.py` — добавить nullable FK в `Expense`, `Income`, `MonthlyBudget`, `SavingsAccount`
- Modify: `tests/conftest.py` — добавить новые модели в `clean_db`

- [ ] **Step 1: Написать failing тест**

Создать файл `tests/test_shared_accounts.py`:

```python
import pytest
from app import app as flask_app, db


def create_user(username, email, password='pw123456'):
    from app import User
    u = User(username=username, email=email)
    u.set_password(password)
    db.session.add(u)
    db.session.flush()
    return u


def test_shared_account_model_creation():
    from app import SharedAccount, SharedAccountMember, User
    with flask_app.app_context():
        u = create_user('owner1', 'owner1@test.com')
        sa = SharedAccount(name='Family Budget', created_by_user_id=u.id)
        db.session.add(sa)
        db.session.flush()
        m = SharedAccountMember(shared_account_id=sa.id, user_id=u.id)
        db.session.add(m)
        db.session.commit()
        assert SharedAccount.query.filter_by(name='Family Budget').count() == 1
        assert SharedAccountMember.query.filter_by(user_id=u.id).count() == 1


def test_shared_account_cascade_delete():
    from app import SharedAccount, SharedAccountMember, User
    with flask_app.app_context():
        u = create_user('owner2', 'owner2@test.com')
        sa = SharedAccount(name='To Delete', created_by_user_id=u.id)
        db.session.add(sa)
        db.session.flush()
        db.session.add(SharedAccountMember(shared_account_id=sa.id, user_id=u.id))
        db.session.commit()
        db.session.delete(sa)
        db.session.commit()
        assert SharedAccountMember.query.count() == 0
```

- [ ] **Step 2: Запустить тест — убедиться что FAIL**

```
pytest tests/test_shared_accounts.py -v
```

Ожидание: `ImportError: cannot import name 'SharedAccount' from 'app'`

- [ ] **Step 3: Добавить модели SharedAccount и SharedAccountMember в app.py**

Добавить после класса `Debt` (после строки с `user = db.relationship('User', backref=...)`):

```python
class SharedAccount(db.Model):
    __tablename__ = 'shared_accounts'

    id                 = db.Column(db.Integer, primary_key=True)
    name               = db.Column(db.String(100), nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at         = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    members = db.relationship('SharedAccountMember', backref='shared_account',
                              lazy='dynamic', cascade='all, delete-orphan')
    creator = db.relationship('User', foreign_keys=[created_by_user_id])


class SharedAccountMember(db.Model):
    __tablename__ = 'shared_account_members'

    id                = db.Column(db.Integer, primary_key=True)
    shared_account_id = db.Column(db.Integer,
                                  db.ForeignKey('shared_accounts.id', ondelete='CASCADE'),
                                  nullable=False)
    user_id           = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    joined_at         = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('shared_account_id', 'user_id'),)

    user = db.relationship('User', backref=db.backref('shared_memberships', lazy='dynamic'))
```

- [ ] **Step 4: Добавить nullable FK в существующие модели**

В классе `Expense` добавить перед строкой `attachments = db.relationship(...)`:
```python
    shared_account_id  = db.Column(db.Integer, db.ForeignKey('shared_accounts.id'), nullable=True)
    added_by_user_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    shared_account     = db.relationship('SharedAccount', foreign_keys=[shared_account_id],
                                         backref=db.backref('expenses', lazy='dynamic'))
    added_by           = db.relationship('User', foreign_keys=[added_by_user_id])
```

В классе `Income` добавить перед строкой `savings_account = db.relationship(...)`:
```python
    shared_account_id = db.Column(db.Integer, db.ForeignKey('shared_accounts.id'), nullable=True)
    added_by_user_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    shared_account    = db.relationship('SharedAccount', foreign_keys=[shared_account_id],
                                        backref=db.backref('incomes', lazy='dynamic'))
    added_by          = db.relationship('User', foreign_keys=[added_by_user_id])
```

В классе `MonthlyBudget` добавить после поля `amount`:
```python
    shared_account_id = db.Column(db.Integer, db.ForeignKey('shared_accounts.id'), nullable=True)
```

В классе `SavingsAccount` добавить после поля `image_mime`:
```python
    shared_account_id = db.Column(db.Integer, db.ForeignKey('shared_accounts.id'), nullable=True)
```

- [ ] **Step 5: Обновить clean_db в conftest.py**

Найти блок `clean_db` в `tests/conftest.py`. Заменить его содержимое:

```python
@pytest.fixture(autouse=True)
def clean_db():
    """Delete all rows between tests."""
    yield
    with flask_app.app_context():
        from app import (User, Expense, Income, MonthlyBudget,
                         Category, ExpenseAttachment, SavingsAccount, Debt,
                         SharedAccountMember, SharedAccount)
        db.session.query(ExpenseAttachment).delete()
        db.session.query(MonthlyBudget).delete()
        db.session.query(Expense).delete()
        db.session.query(Income).delete()
        db.session.query(Category).delete()
        db.session.query(SavingsAccount).delete()
        db.session.query(Debt).delete()
        db.session.query(SharedAccountMember).delete()
        db.session.query(SharedAccount).delete()
        db.session.query(User).delete()
        db.session.commit()
```

- [ ] **Step 6: Запустить тест — убедиться что PASS**

```
pytest tests/test_shared_accounts.py::test_shared_account_model_creation tests/test_shared_accounts.py::test_shared_account_cascade_delete -v
```

Ожидание: оба PASS

- [ ] **Step 7: Прогнать все существующие тесты — убедиться нет регрессий**

```
pytest tests/ -v --tb=short
```

Ожидание: все тесты PASS

- [ ] **Step 8: Написать SQL миграцию для прод-БД**

Создать файл `migrations/001_shared_accounts.sql`:

```sql
CREATE TABLE IF NOT EXISTS shared_accounts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    created_by_user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS shared_account_members (
    id SERIAL PRIMARY KEY,
    shared_account_id INTEGER NOT NULL REFERENCES shared_accounts(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    joined_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(shared_account_id, user_id)
);

ALTER TABLE expenses ADD COLUMN IF NOT EXISTS shared_account_id INTEGER REFERENCES shared_accounts(id);
ALTER TABLE expenses ADD COLUMN IF NOT EXISTS added_by_user_id INTEGER REFERENCES users(id);
ALTER TABLE incomes ADD COLUMN IF NOT EXISTS shared_account_id INTEGER REFERENCES shared_accounts(id);
ALTER TABLE incomes ADD COLUMN IF NOT EXISTS added_by_user_id INTEGER REFERENCES users(id);
ALTER TABLE monthly_budgets ADD COLUMN IF NOT EXISTS shared_account_id INTEGER REFERENCES shared_accounts(id);
ALTER TABLE savings_accounts ADD COLUMN IF NOT EXISTS shared_account_id INTEGER REFERENCES shared_accounts(id);
```

- [ ] **Step 9: Commit**

```
git add app.py tests/conftest.py tests/test_shared_accounts.py migrations/001_shared_accounts.sql
git commit -m "feat: add SharedAccount and SharedAccountMember models with FK columns"
```

---

## Task 2: Context helpers и декоратор

**Files:**
- Modify: `app.py` — добавить `get_active_context()`, `shared_member_required`, `inject_shared_accounts` context processor

- [ ] **Step 1: Написать failing тест**

Добавить в `tests/test_shared_accounts.py`:

```python
def login(client, username, password='pw123456'):
    return client.post('/login', data={'username': username, 'password': password,
                                       'next': ''}, follow_redirects=True)


def test_switch_to_shared_context(client):
    from app import SharedAccount, SharedAccountMember, User
    with flask_app.app_context():
        u = create_user('ctx_user', 'ctx@test.com')
        sa = SharedAccount(name='Test Account', created_by_user_id=u.id)
        db.session.add(sa)
        db.session.flush()
        db.session.add(SharedAccountMember(shared_account_id=sa.id, user_id=u.id))
        db.session.commit()
        sa_id = sa.id

    login(client, 'ctx_user')
    resp = client.get(f'/shared/switch/{sa_id}', follow_redirects=True)
    assert resp.status_code == 200

    with client.session_transaction() as sess:
        assert sess.get('active_shared_account_id') == sa_id


def test_switch_to_personal_context(client):
    from app import SharedAccount, SharedAccountMember, User
    with flask_app.app_context():
        u = create_user('ctx_user2', 'ctx2@test.com')
        sa = SharedAccount(name='Test Account2', created_by_user_id=u.id)
        db.session.add(sa)
        db.session.flush()
        db.session.add(SharedAccountMember(shared_account_id=sa.id, user_id=u.id))
        db.session.commit()
        sa_id = sa.id

    login(client, 'ctx_user2')
    client.get(f'/shared/switch/{sa_id}')
    client.get('/shared/switch/personal')

    with client.session_transaction() as sess:
        assert sess.get('active_shared_account_id') is None


def test_non_member_switch_rejected(client):
    from app import SharedAccount, SharedAccountMember, User
    with flask_app.app_context():
        owner = create_user('owner_nm', 'owner_nm@test.com')
        other = create_user('other_nm', 'other_nm@test.com')
        sa = SharedAccount(name='Private', created_by_user_id=owner.id)
        db.session.add(sa)
        db.session.flush()
        db.session.add(SharedAccountMember(shared_account_id=sa.id, user_id=owner.id))
        db.session.commit()
        sa_id = sa.id

    login(client, 'other_nm')
    resp = client.get(f'/shared/switch/{sa_id}', follow_redirects=False)
    assert resp.status_code in (302, 403)
```

- [ ] **Step 2: Запустить — убедиться что FAIL**

```
pytest tests/test_shared_accounts.py::test_switch_to_shared_context -v
```

Ожидание: `404` (маршрут не существует)

- [ ] **Step 3: Добавить get_active_context() и shared_member_required в app.py**

Найти раздел `# ─── Декораторы ───` (около строки 282). Добавить перед ним:

```python
# ─── Shared account helpers ───────────────────────────────────────────────────

def get_active_context():
    """Return ('personal', user_id) or ('shared', shared_account_id)."""
    shared_id = session.get('active_shared_account_id')
    if shared_id:
        membership = SharedAccountMember.query.filter_by(
            shared_account_id=shared_id,
            user_id=current_user.id,
        ).first()
        if membership:
            return 'shared', shared_id
        session.pop('active_shared_account_id', None)
    return 'personal', current_user.id


def shared_member_required(f):
    """Abort 403 if current_user is not a member of shared_account_id URL param."""
    @wraps(f)
    def decorated(shared_id, *args, **kwargs):
        m = SharedAccountMember.query.filter_by(
            shared_account_id=shared_id,
            user_id=current_user.id,
        ).first()
        if not m:
            abort(403)
        return f(shared_id, *args, **kwargs)
    return decorated
```

- [ ] **Step 4: Добавить маршруты переключения контекста в app.py**

Добавить в конец раздела маршрутов (перед `if __name__ == '__main__'` или в конце файла):

```python
# ─── Shared account routes ────────────────────────────────────────────────────

@app.route('/shared/switch/<int:shared_id>')
@login_required
@ban_check
def shared_switch(shared_id):
    m = SharedAccountMember.query.filter_by(
        shared_account_id=shared_id, user_id=current_user.id
    ).first()
    if not m:
        flash('Вы не являетесь участником этого счёта.', 'danger')
        return redirect(url_for('index'))
    session['active_shared_account_id'] = shared_id
    flash(f'Переключено на: {m.shared_account.name}', 'info')
    return redirect(request.referrer or url_for('index'))


@app.route('/shared/switch/personal')
@login_required
def shared_switch_personal():
    session.pop('active_shared_account_id', None)
    flash('Переключено на личный счёт.', 'info')
    return redirect(request.referrer or url_for('index'))
```

- [ ] **Step 5: Добавить context processor для инжекции shared accounts в шаблоны**

Добавить после существующих context processor'ов (после `inject_debt_summary`):

```python
@app.context_processor
def inject_shared_context():
    if not current_user.is_authenticated:
        return {'user_shared_accounts': [], 'active_shared_account': None}
    memberships = SharedAccountMember.query.filter_by(
        user_id=current_user.id
    ).all()
    accounts = [m.shared_account for m in memberships]
    active_id = session.get('active_shared_account_id')
    active = next((a for a in accounts if a.id == active_id), None)
    return {'user_shared_accounts': accounts, 'active_shared_account': active}
```

- [ ] **Step 6: Запустить тесты — убедиться что PASS**

```
pytest tests/test_shared_accounts.py::test_switch_to_shared_context tests/test_shared_accounts.py::test_switch_to_personal_context tests/test_shared_accounts.py::test_non_member_switch_rejected -v
```

Ожидание: все три PASS

- [ ] **Step 7: Commit**

```
git add app.py
git commit -m "feat: add get_active_context helper, shared_member_required decorator and context switcher routes"
```

---

## Task 3: Маршруты управления совместным счётом

**Files:**
- Modify: `app.py` — добавить маршруты create, manage, invite, leave

- [ ] **Step 1: Написать failing тест**

Добавить в `tests/test_shared_accounts.py`:

```python
def test_create_shared_account(client):
    from app import SharedAccount, SharedAccountMember, User
    with flask_app.app_context():
        create_user('creator1', 'creator1@test.com')
    login(client, 'creator1')

    resp = client.post('/shared/create',
                       data={'name': 'Family Budget'},
                       follow_redirects=True)
    assert resp.status_code == 200

    with flask_app.app_context():
        sa = SharedAccount.query.filter_by(name='Family Budget').first()
        assert sa is not None
        assert SharedAccountMember.query.filter_by(shared_account_id=sa.id).count() == 1


def test_invite_existing_user(client):
    from app import SharedAccount, SharedAccountMember, User
    with flask_app.app_context():
        owner = create_user('inv_owner', 'inv_owner@test.com')
        invitee = create_user('inv_target', 'inv_target@test.com')
        sa = SharedAccount(name='Invite Test', created_by_user_id=owner.id)
        db.session.add(sa)
        db.session.flush()
        db.session.add(SharedAccountMember(shared_account_id=sa.id, user_id=owner.id))
        db.session.commit()
        sa_id = sa.id

    login(client, 'inv_owner')
    resp = client.post(f'/shared/{sa_id}/invite',
                       data={'identifier': 'inv_target'},
                       follow_redirects=True)
    assert resp.status_code == 200

    with flask_app.app_context():
        assert SharedAccountMember.query.filter_by(shared_account_id=sa_id).count() == 2


def test_invite_nonexistent_user(client):
    from app import SharedAccount, SharedAccountMember, User
    with flask_app.app_context():
        owner = create_user('inv_owner2', 'inv_owner2@test.com')
        sa = SharedAccount(name='Test2', created_by_user_id=owner.id)
        db.session.add(sa)
        db.session.flush()
        db.session.add(SharedAccountMember(shared_account_id=sa.id, user_id=owner.id))
        db.session.commit()
        sa_id = sa.id

    login(client, 'inv_owner2')
    resp = client.post(f'/shared/{sa_id}/invite',
                       data={'identifier': 'nobody_exists'},
                       follow_redirects=True)
    assert resp.status_code == 200
    with flask_app.app_context():
        assert SharedAccountMember.query.filter_by(shared_account_id=sa_id).count() == 1


def test_leave_last_member_deletes_account(client):
    from app import SharedAccount, SharedAccountMember, User
    with flask_app.app_context():
        u = create_user('leaver', 'leaver@test.com')
        sa = SharedAccount(name='Doomed', created_by_user_id=u.id)
        db.session.add(sa)
        db.session.flush()
        db.session.add(SharedAccountMember(shared_account_id=sa.id, user_id=u.id))
        db.session.commit()
        sa_id = sa.id

    login(client, 'leaver')
    resp = client.post(f'/shared/{sa_id}/leave', follow_redirects=True)
    assert resp.status_code == 200

    with flask_app.app_context():
        assert SharedAccount.query.get(sa_id) is None
```

- [ ] **Step 2: Запустить — убедиться что FAIL**

```
pytest tests/test_shared_accounts.py::test_create_shared_account -v
```

Ожидание: `404`

- [ ] **Step 3: Добавить маршруты create, manage, invite, leave в app.py**

Добавить после маршрутов `shared_switch` и `shared_switch_personal`:

```python
@app.route('/shared/create', methods=['GET', 'POST'])
@login_required
@ban_check
def shared_create():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name or len(name) > 100:
            flash('Введите название счёта (до 100 символов).', 'danger')
            return redirect(url_for('shared_create'))
        sa = SharedAccount(name=name, created_by_user_id=current_user.id)
        db.session.add(sa)
        db.session.flush()
        db.session.add(SharedAccountMember(
            shared_account_id=sa.id, user_id=current_user.id
        ))
        db.session.commit()
        session['active_shared_account_id'] = sa.id
        flash(f'Совместный счёт «{sa.name}» создан!', 'success')
        return redirect(url_for('shared_manage', shared_id=sa.id))
    return render_template('shared/manage.html', account=None, members=[])


@app.route('/shared/<int:shared_id>')
@login_required
@ban_check
@shared_member_required
def shared_manage(shared_id):
    sa = db.session.get(SharedAccount, shared_id)
    if not sa:
        abort(404)
    members = SharedAccountMember.query.filter_by(
        shared_account_id=shared_id
    ).all()
    return render_template('shared/manage.html', account=sa, members=members)


@app.route('/shared/<int:shared_id>/invite', methods=['POST'])
@login_required
@ban_check
@shared_member_required
def shared_invite(shared_id):
    identifier = request.form.get('identifier', '').strip()
    if not identifier:
        flash('Введите логин или email.', 'danger')
        return redirect(url_for('shared_manage', shared_id=shared_id))

    target = User.query.filter(
        db.or_(User.username == identifier, User.email == identifier)
    ).first()
    if not target:
        flash('Пользователь не найден.', 'danger')
        return redirect(url_for('shared_manage', shared_id=shared_id))

    existing = SharedAccountMember.query.filter_by(
        shared_account_id=shared_id, user_id=target.id
    ).first()
    if existing:
        flash(f'{target.username} уже является участником.', 'warning')
        return redirect(url_for('shared_manage', shared_id=shared_id))

    db.session.add(SharedAccountMember(
        shared_account_id=shared_id, user_id=target.id
    ))
    db.session.commit()
    flash(f'{target.username} добавлен в счёт.', 'success')
    return redirect(url_for('shared_manage', shared_id=shared_id))


@app.route('/shared/<int:shared_id>/leave', methods=['POST'])
@login_required
@ban_check
@shared_member_required
def shared_leave(shared_id):
    sa = db.session.get(SharedAccount, shared_id)
    if not sa:
        abort(404)

    member_count = SharedAccountMember.query.filter_by(
        shared_account_id=shared_id
    ).count()

    m = SharedAccountMember.query.filter_by(
        shared_account_id=shared_id, user_id=current_user.id
    ).first()
    db.session.delete(m)

    if member_count == 1:
        db.session.delete(sa)
        db.session.commit()
        if session.get('active_shared_account_id') == shared_id:
            session.pop('active_shared_account_id', None)
        flash('Счёт удалён (последний участник покинул).', 'warning')
    else:
        db.session.commit()
        if session.get('active_shared_account_id') == shared_id:
            session.pop('active_shared_account_id', None)
        flash('Вы покинули совместный счёт.', 'info')

    return redirect(url_for('index'))
```

- [ ] **Step 4: Запустить тесты — убедиться что PASS**

```
pytest tests/test_shared_accounts.py::test_create_shared_account tests/test_shared_accounts.py::test_invite_existing_user tests/test_shared_accounts.py::test_invite_nonexistent_user tests/test_shared_accounts.py::test_leave_last_member_deletes_account -v
```

Ожидание: все четыре PASS

- [ ] **Step 5: Commit**

```
git add app.py
git commit -m "feat: add shared account create/manage/invite/leave routes"
```

---

## Task 4: Шаблон manage.html

**Files:**
- Create: `templates/shared/manage.html`

- [ ] **Step 1: Создать директорию и шаблон**

Создать файл `templates/shared/manage.html`:

```html
{% extends 'base.html' %}
{% block title %}Совместный счёт{% endblock %}

{% block content %}
<div class="container py-4">

{% if account is none %}
  {# Форма создания нового счёта #}
  <h2 class="mb-4">Создать совместный счёт</h2>
  <div class="card shadow-sm" style="max-width:480px">
    <div class="card-body">
      <form method="post" action="{{ url_for('shared_create') }}">
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
        <div class="mb-3">
          <label class="form-label fw-semibold">Название счёта</label>
          <input type="text" name="name" class="form-control"
                 placeholder="Семейный бюджет" maxlength="100" required autofocus>
        </div>
        <button type="submit" class="btn btn-primary w-100">Создать</button>
      </form>
    </div>
  </div>
{% else %}
  {# Страница управления существующим счётом #}
  <div class="d-flex justify-content-between align-items-center mb-4">
    <h2 class="mb-0">{{ account.name }}</h2>
    <form method="post" action="{{ url_for('shared_leave', shared_id=account.id) }}"
          onsubmit="return confirm('Покинуть счёт?')">
      <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
      <button type="submit" class="btn btn-outline-danger btn-sm">Покинуть счёт</button>
    </form>
  </div>

  <div class="row g-4">
    <div class="col-md-6">
      <div class="card shadow-sm">
        <div class="card-header fw-semibold">Участники ({{ members|length }})</div>
        <ul class="list-group list-group-flush">
          {% for m in members %}
          <li class="list-group-item d-flex align-items-center gap-2">
            <span class="fs-4">{{ m.user.avatar or '👤' }}</span>
            <div>
              <div class="fw-semibold">{{ m.user.username }}</div>
              <small class="text-muted">с {{ m.joined_at.strftime('%d.%m.%Y') }}</small>
            </div>
            {% if m.user_id == account.created_by_user_id %}
            <span class="badge bg-primary ms-auto">создатель</span>
            {% endif %}
          </li>
          {% endfor %}
        </ul>
      </div>
    </div>

    <div class="col-md-6">
      <div class="card shadow-sm">
        <div class="card-header fw-semibold">Пригласить участника</div>
        <div class="card-body">
          <form method="post" action="{{ url_for('shared_invite', shared_id=account.id) }}">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
            <div class="mb-3">
              <label class="form-label">Логин или email</label>
              <input type="text" name="identifier" class="form-control"
                     placeholder="username или email@example.com" required>
            </div>
            <button type="submit" class="btn btn-success w-100">Пригласить</button>
          </form>
        </div>
      </div>
    </div>
  </div>
{% endif %}

</div>
{% endblock %}
```

- [ ] **Step 2: Проверить что маршрут /shared/create рендерится без ошибок**

```
pytest tests/test_shared_accounts.py::test_create_shared_account -v
```

Ожидание: PASS (шаблон рендерится без ошибок)

- [ ] **Step 3: Commit**

```
git add templates/shared/manage.html
git commit -m "feat: add shared account manage template"
```

---

## Task 5: Обновить маршруты расходов для контекста

**Files:**
- Modify: `app.py` — `expenses_list`, `expense_add`, `expense_edit`, `expense_delete`, `expense_toggle_spent`

- [ ] **Step 1: Написать failing тест**

Добавить в `tests/test_shared_accounts.py`:

```python
def test_expense_created_in_shared_context(client):
    from app import SharedAccount, SharedAccountMember, User, Expense, Category
    with flask_app.app_context():
        u = create_user('exp_user', 'exp_user@test.com')
        sa = SharedAccount(name='Exp Account', created_by_user_id=u.id)
        db.session.add(sa)
        db.session.flush()
        db.session.add(SharedAccountMember(shared_account_id=sa.id, user_id=u.id))
        cat = Category(name='Food', color='#ff0000')
        db.session.add(cat)
        db.session.commit()
        sa_id = sa.id
        cat_id = cat.id

    login(client, 'exp_user')
    client.get(f'/shared/switch/{sa_id}')

    resp = client.post('/expenses/add', data={
        'category_id': cat_id,
        'amount': '500',
        'description': 'Shared groceries',
        'expense_date': '2024-05-01',
        'is_planned': 'on',
        'is_spent': 'on',
    }, follow_redirects=True)
    assert resp.status_code == 200

    with flask_app.app_context():
        exp = Expense.query.filter_by(description='Shared groceries').first()
        assert exp is not None
        assert exp.shared_account_id == sa_id
        assert exp.added_by_user_id == User.query.filter_by(username='exp_user').first().id


def test_expense_list_in_shared_context_shows_shared_expenses(client):
    from app import SharedAccount, SharedAccountMember, User, Expense, Category
    from datetime import date as dt
    with flask_app.app_context():
        u = create_user('list_user', 'list_user@test.com')
        sa = SharedAccount(name='List Account', created_by_user_id=u.id)
        db.session.add(sa)
        db.session.flush()
        db.session.add(SharedAccountMember(shared_account_id=sa.id, user_id=u.id))
        cat = Category(name='Transport', color='#0000ff')
        db.session.add(cat)
        db.session.flush()
        # Personal expense
        db.session.add(Expense(user_id=u.id, category_id=cat.id, amount=100,
                                expense_date=dt(2024, 5, 1), is_planned=True, is_spent=True))
        # Shared expense
        db.session.add(Expense(user_id=u.id, category_id=cat.id, amount=200,
                                expense_date=dt(2024, 5, 1), is_planned=True, is_spent=True,
                                shared_account_id=sa.id, added_by_user_id=u.id))
        db.session.commit()
        sa_id = sa.id

    login(client, 'list_user')

    # Personal context — see personal expense only
    resp = client.get('/expenses?year=2024&month=5')
    assert b'100' in resp.data
    # 200 might appear as text "200" in amount — let's check it's not the shared one
    # by checking shared_account expense description is absent (there's none here)

    # Shared context — see shared expense only
    client.get(f'/shared/switch/{sa_id}')
    resp = client.get('/expenses?year=2024&month=5')
    assert resp.status_code == 200
```

- [ ] **Step 2: Запустить — убедиться что FAIL**

```
pytest tests/test_shared_accounts.py::test_expense_created_in_shared_context -v
```

Ожидание: FAIL (расход создаётся без shared_account_id)

- [ ] **Step 3: Обновить expenses_list в app.py**

Найти маршрут `expenses_list` (около строки 1384). Заменить блок фильтрации:

```python
@app.route('/expenses')
@login_required
@ban_check
def expenses_list():
    today  = date.today()
    year   = int(request.args.get('year',  today.year))
    month  = int(request.args.get('month', today.month))
    cat_id       = request.args.get('category_id', type=int)
    spent_filter = request.args.get('spent', 'all')

    ctx_type, ctx_id = get_active_context()
    if ctx_type == 'shared':
        query = Expense.query.filter(
            Expense.shared_account_id == ctx_id,
            extract('year',  Expense.expense_date) == year,
            extract('month', Expense.expense_date) == month,
        )
    else:
        query = Expense.query.filter(
            Expense.user_id == ctx_id,
            Expense.shared_account_id.is_(None),
            extract('year',  Expense.expense_date) == year,
            extract('month', Expense.expense_date) == month,
        )

    if cat_id:
        query = query.filter(Expense.category_id == cat_id)
    if spent_filter == 'spent':
        query = query.filter(Expense.is_spent.is_(True))
    elif spent_filter == 'unspent':
        query = query.filter(Expense.is_spent.is_(False))

    sort = request.args.get('sort', 'date_desc')
    if sort == 'date_asc':
        query = query.order_by(Expense.expense_date.asc(), Expense.created_at.asc())
    elif sort == 'amount_desc':
        query = query.order_by(Expense.amount.desc())
    elif sort == 'amount_asc':
        query = query.order_by(Expense.amount.asc())
    elif sort == 'category_asc':
        query = query.join(Category).order_by(Category.name.asc())
    else:
        sort = 'date_desc'
        query = query.order_by(Expense.expense_date.desc(), Expense.created_at.desc())

    expenses   = query.options(joinedload(Expense.attachments)).all()
    categories = Category.query.filter(
        Category.is_active.is_(True),
        db.or_(Category.user_id.is_(None), Category.user_id == current_user.id)
    ).order_by(Category.name).all()

    att_data = {
        exp.id: [{'id': a.id, 'mime': a.mime_type, 'fname': a.filename} for a in exp.attachments]
        for exp in expenses if exp.attachments
    }

    return render_template('expenses/list.html',
        expenses=expenses, categories=categories, att_data=att_data,
        year=year, month=month, months=months_list(), selected_cat=cat_id, sort=sort,
        spent_filter=spent_filter,
        active_shared_account=session.get('active_shared_account_id'))
```

- [ ] **Step 4: Обновить expense_add в app.py**

В маршруте `expense_add`, найти строку создания объекта `Expense(...)` и заменить:

```python
    if request.method == 'POST':
        ctx_type, ctx_id = get_active_context()
        try:
            exp = Expense(
                user_id      = current_user.id,
                category_id  = int(request.form['category_id']),
                amount       = float(request.form['amount']),
                description  = request.form.get('description', '').strip() or None,
                expense_date = datetime.strptime(request.form['expense_date'], '%Y-%m-%d').date(),
                is_planned   = request.form.get('is_planned') == 'on',
                is_spent     = request.form.get('is_spent') == 'on',
                notes        = request.form.get('notes', '').strip() or None,
                shared_account_id = ctx_id if ctx_type == 'shared' else None,
                added_by_user_id  = current_user.id if ctx_type == 'shared' else None,
            )
```

- [ ] **Step 5: Добавить хелпер get_expense_or_403 и обновить edit/delete/toggle**

Добавить хелпер перед маршрутом `expense_edit`:

```python
def get_expense_or_403(exp_id):
    """Return expense if current_user owns it (personal) or is member of its shared account."""
    exp = db.session.get(Expense, exp_id)
    if not exp:
        abort(404)
    if exp.shared_account_id:
        m = SharedAccountMember.query.filter_by(
            shared_account_id=exp.shared_account_id,
            user_id=current_user.id,
        ).first()
        if not m:
            abort(403)
    elif exp.user_id != current_user.id:
        abort(403)
    return exp
```

В `expense_edit` заменить строку:
```python
exp = Expense.query.filter_by(id=exp_id, user_id=current_user.id).first_or_404()
```
на:
```python
exp = get_expense_or_403(exp_id)
```

В `expense_delete` заменить строку:
```python
exp = Expense.query.filter_by(id=exp_id, user_id=current_user.id).first_or_404()
```
на:
```python
exp = get_expense_or_403(exp_id)
```

В `expense_toggle_spent` заменить:
```python
exp = Expense.query.filter_by(id=exp_id, user_id=current_user.id).first()
if not exp:
    abort(403)
```
на:
```python
exp = get_expense_or_403(exp_id)
```

- [ ] **Step 6: Запустить тесты — убедиться что PASS**

```
pytest tests/test_shared_accounts.py::test_expense_created_in_shared_context tests/test_shared_accounts.py::test_expense_list_in_shared_context_shows_shared_expenses -v
```

Ожидание: оба PASS

- [ ] **Step 7: Прогнать все тесты**

```
pytest tests/ -v --tb=short
```

Ожидание: все PASS

- [ ] **Step 8: Commit**

```
git add app.py
git commit -m "feat: update expense routes to respect shared account context"
```

---

## Task 6: Обновить маршруты доходов для контекста

**Files:**
- Modify: `app.py` — income-маршруты

- [ ] **Step 1: Найти маршрут income_list и обновить фильтрацию**

Найти маршрут `income_list` (grep: `@app.route('/income')`). Заменить фильтрацию аналогично расходам:

```python
@app.route('/income')
@login_required
@ban_check
def income_list():
    today = date.today()
    year  = int(request.args.get('year',  today.year))
    month = int(request.args.get('month', today.month))

    ctx_type, ctx_id = get_active_context()
    if ctx_type == 'shared':
        incomes = Income.query.filter(
            Income.shared_account_id == ctx_id,
            extract('year',  Income.income_date) == year,
            extract('month', Income.income_date) == month,
        ).order_by(Income.income_date.desc()).all()
    else:
        incomes = Income.query.filter(
            Income.user_id == ctx_id,
            Income.shared_account_id.is_(None),
            extract('year',  Income.income_date) == year,
            extract('month', Income.income_date) == month,
        ).order_by(Income.income_date.desc()).all()

    return render_template('income/list.html', incomes=incomes,
                           year=year, month=month, months=months_list())
```

- [ ] **Step 2: Найти маршрут income_add и обновить создание дохода**

Найти `income_add`. В строке создания `Income(...)` добавить:
```python
            inc = Income(
                user_id     = current_user.id,
                amount      = float(request.form['amount']),
                source      = request.form['source'].strip(),
                description = request.form.get('description', '').strip() or None,
                income_date = datetime.strptime(request.form['income_date'], '%Y-%m-%d').date(),
                notes       = request.form.get('notes', '').strip() or None,
                shared_account_id = ctx_id if ctx_type == 'shared' else None,
                added_by_user_id  = current_user.id if ctx_type == 'shared' else None,
            )
```

Добавить перед созданием `Income`:
```python
        ctx_type, ctx_id = get_active_context()
```

- [ ] **Step 3: Добавить хелпер get_income_or_403 и обновить edit/delete**

```python
def get_income_or_403(inc_id):
    inc = db.session.get(Income, inc_id)
    if not inc:
        abort(404)
    if inc.shared_account_id:
        m = SharedAccountMember.query.filter_by(
            shared_account_id=inc.shared_account_id,
            user_id=current_user.id,
        ).first()
        if not m:
            abort(403)
    elif inc.user_id != current_user.id:
        abort(403)
    return inc
```

В `income_edit` и `income_delete` заменить `Income.query.filter_by(id=inc_id, user_id=current_user.id).first_or_404()` на `get_income_or_403(inc_id)`.

- [ ] **Step 4: Запустить все тесты**

```
pytest tests/ -v --tb=short
```

Ожидание: все PASS

- [ ] **Step 5: Commit**

```
git add app.py
git commit -m "feat: update income routes to respect shared account context"
```

---

## Task 7: Обновить главный дашборд и хелперы для контекста

**Files:**
- Modify: `app.py` — `get_monthly_income`, `get_monthly_summary`, `get_budget_map`, `index`

- [ ] **Step 1: Обновить get_monthly_income**

Заменить функцию `get_monthly_income`:

```python
def get_monthly_income(user_id=None, year=None, month=None, shared_account_id=None):
    q = db.session.query(func.coalesce(func.sum(Income.amount), 0)).filter(
        extract('year',  Income.income_date) == year,
        extract('month', Income.income_date) == month,
        Income.savings_account_id.is_(None),
    )
    if shared_account_id:
        q = q.filter(Income.shared_account_id == shared_account_id)
    else:
        q = q.filter(Income.user_id == user_id, Income.shared_account_id.is_(None))
    return float(q.scalar())
```

- [ ] **Step 2: Обновить get_monthly_summary**

Найти `get_monthly_summary`. Заменить сигнатуру и внутренний join:

```python
def get_monthly_summary(user_id=None, year=None, month=None, shared_account_id=None):
    if shared_account_id:
        expense_filter = (
            (Expense.shared_account_id == shared_account_id)
            & (Expense.is_spent.is_(True))
            & (extract('year',  Expense.expense_date) == year)
            & (extract('month', Expense.expense_date) == month)
        )
    else:
        expense_filter = (
            (Expense.user_id == user_id)
            & (Expense.shared_account_id.is_(None))
            & (Expense.is_spent.is_(True))
            & (extract('year',  Expense.expense_date) == year)
            & (extract('month', Expense.expense_date) == month)
        )

    rows = (
        db.session.query(
            Category.id,
            Category.name,
            Category.color,
            Category.icon,
            func.coalesce(func.sum(Expense.amount), 0).label('total'),
        )
        .outerjoin(Expense, (Expense.category_id == Category.id) & expense_filter)
        .filter(
            Category.is_active.is_(True),
            db.or_(Category.user_id.is_(None), Category.user_id == (user_id or current_user.id))
        )
        .group_by(Category.id, Category.name, Category.color, Category.icon)
        .order_by(func.coalesce(func.sum(Expense.amount), 0).desc())
        .all()
    )
    return rows
```

- [ ] **Step 3: Обновить get_budget_map**

```python
def get_budget_map(user_id=None, year=None, month=None, shared_account_id=None):
    if shared_account_id:
        budgets = MonthlyBudget.query.filter_by(
            shared_account_id=shared_account_id, year=year, month=month
        ).all()
    else:
        budgets = MonthlyBudget.query.filter(
            MonthlyBudget.user_id == user_id,
            MonthlyBudget.shared_account_id.is_(None),
            MonthlyBudget.year == year,
            MonthlyBudget.month == month,
        ).all()
    return {b.category_id: float(b.amount) for b in budgets}
```

- [ ] **Step 4: Обновить маршрут index**

В начале маршрута `index`, после `today`/`year`/`month`, заменить:
```python
    uid = current_user.id
    summary      = get_monthly_summary(uid, year, month)
    budget_map   = get_budget_map(uid, year, month)
    total_income = get_monthly_income(uid, year, month)
```
на:
```python
    ctx_type, ctx_id = get_active_context()
    if ctx_type == 'shared':
        summary      = get_monthly_summary(year=year, month=month, shared_account_id=ctx_id)
        budget_map   = get_budget_map(year=year, month=month, shared_account_id=ctx_id)
        total_income = get_monthly_income(year=year, month=month, shared_account_id=ctx_id)
        recent = (
            Expense.query
            .filter(
                Expense.shared_account_id == ctx_id,
                extract('year',  Expense.expense_date) == year,
                extract('month', Expense.expense_date) == month,
            )
            .order_by(Expense.expense_date.desc(), Expense.created_at.desc())
            .limit(5).all()
        )
        savings_accounts = SavingsAccount.query.filter_by(
            shared_account_id=ctx_id, is_active=True
        ).order_by(SavingsAccount.created_at.asc()).all()
        uid = current_user.id
        can_copy = False
    else:
        uid          = current_user.id
        summary      = get_monthly_summary(user_id=uid, year=year, month=month)
        budget_map   = get_budget_map(user_id=uid, year=year, month=month)
        total_income = get_monthly_income(user_id=uid, year=year, month=month)
        recent = (
            Expense.query
            .filter(
                Expense.user_id == uid,
                Expense.shared_account_id.is_(None),
                extract('year',  Expense.expense_date) == year,
                extract('month', Expense.expense_date) == month,
            )
            .order_by(Expense.expense_date.desc(), Expense.created_at.desc())
            .limit(5).all()
        )
        savings_accounts = SavingsAccount.query.filter_by(
            user_id=uid, is_active=True, shared_account_id=None
        ).order_by(SavingsAccount.created_at.asc()).all()
```

Удалить старые строки `recent` и `savings_accounts` в ветке `else` (они дублируются). Оставить остальную логику (`can_copy`, `daily_info`, etc.) только в ветке `else` или после всего блока if/else.

Полный блок `index` после рефакторинга:

```python
@app.route('/')
@login_required
@ban_check
def index():
    today = date.today()
    year  = int(request.args.get('year',  today.year))
    month = int(request.args.get('month', today.month))

    ctx_type, ctx_id = get_active_context()

    if ctx_type == 'shared':
        summary      = get_monthly_summary(year=year, month=month, shared_account_id=ctx_id)
        budget_map   = get_budget_map(year=year, month=month, shared_account_id=ctx_id)
        total_income = get_monthly_income(year=year, month=month, shared_account_id=ctx_id)
        recent = (
            Expense.query
            .filter(
                Expense.shared_account_id == ctx_id,
                extract('year',  Expense.expense_date) == year,
                extract('month', Expense.expense_date) == month,
            )
            .order_by(Expense.expense_date.desc(), Expense.created_at.desc())
            .limit(5).all()
        )
        savings_accounts = SavingsAccount.query.filter_by(
            shared_account_id=ctx_id, is_active=True
        ).order_by(SavingsAccount.created_at.asc()).all()
        can_copy = False
        daily_info = None
    else:
        uid          = current_user.id
        summary      = get_monthly_summary(user_id=uid, year=year, month=month)
        budget_map   = get_budget_map(user_id=uid, year=year, month=month)
        total_income = get_monthly_income(user_id=uid, year=year, month=month)
        recent = (
            Expense.query
            .filter(
                Expense.user_id == uid,
                Expense.shared_account_id.is_(None),
                extract('year',  Expense.expense_date) == year,
                extract('month', Expense.expense_date) == month,
            )
            .order_by(Expense.expense_date.desc(), Expense.created_at.desc())
            .limit(5).all()
        )
        savings_accounts = SavingsAccount.query.filter_by(
            user_id=uid, is_active=True, shared_account_id=None
        ).order_by(SavingsAccount.created_at.asc()).all()

        total_spent  = sum(float(r.total) for r in summary)
        balance      = total_income - total_spent
        prev_month = month - 1 if month > 1 else 12
        prev_year  = year if month > 1 else year - 1
        current_empty = (total_spent == 0 and total_income == 0)
        prev_has_expenses = Expense.query.filter_by(
            user_id=uid, is_planned=True
        ).filter(
            extract('year',  Expense.expense_date) == prev_year,
            extract('month', Expense.expense_date) == prev_month,
        ).count() > 0
        prev_has_income = Income.query.filter(
            Income.user_id == uid,
            Income.shared_account_id.is_(None),
            extract('year',  Income.income_date) == prev_year,
            extract('month', Income.income_date) == prev_month,
        ).count() > 0
        can_copy = current_empty and (prev_has_expenses or prev_has_income)
        daily_info = get_daily_budget_info(
            balance=balance,
            salary_day=current_user.salary_day,
            advance_day=current_user.advance_day,
        )

    total_spent  = sum(float(r.total) for r in summary)
    balance      = total_income - total_spent

    prev_month = month - 1 if month > 1 else 12
    prev_year  = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year  = year if month < 12 else year + 1

    alert_pct = current_user.budget_alert_pct
    alert_map = {}
    for row in summary:
        _budget = budget_map.get(row.id, 0)
        if _budget <= 0:
            continue
        _spent = float(row.total or 0)
        _pct   = _spent / _budget * 100
        if _spent > _budget:
            alert_map[row.id] = 'exceeded'
        elif _pct >= alert_pct:
            alert_map[row.id] = 'warning'

    savings_data = []
    for acc in savings_accounts:
        bal = get_account_balance(acc.id)
        pct = None
        if acc.target_amount and float(acc.target_amount) > 0:
            pct = min(round(bal / float(acc.target_amount) * 100, 1), 100.0)
        savings_data.append({'acc': acc, 'balance': bal, 'pct': pct})

    return render_template('index.html',
        summary=summary, budget_map=budget_map,
        total_spent=total_spent, total_income=total_income, balance=balance,
        recent=recent, year=year, month=month, today=today, months=months_list(),
        daily_info=daily_info,
        salary_day=current_user.salary_day,
        advance_day=current_user.advance_day,
        can_copy=can_copy,
        savings_data=savings_data,
        alert_map=alert_map,
        prev_month=prev_month, prev_year=prev_year,
        next_month=next_month, next_year=next_year,
    )
```

- [ ] **Step 5: Обновить inject_budget_alerts context processor**

Найти `inject_budget_alerts`. Заменить:

```python
@app.context_processor
def inject_budget_alerts():
    if not current_user.is_authenticated:
        return {'budget_alerts': []}
    today_   = date.today()
    ctx_type, ctx_id = get_active_context()
    if ctx_type == 'shared':
        summary = get_monthly_summary(year=today_.year, month=today_.month, shared_account_id=ctx_id)
        bmap    = get_budget_map(year=today_.year, month=today_.month, shared_account_id=ctx_id)
    else:
        summary = get_monthly_summary(user_id=ctx_id, year=today_.year, month=today_.month)
        bmap    = get_budget_map(user_id=ctx_id, year=today_.year, month=today_.month)
    threshold = current_user.budget_alert_pct
    alerts = []
    for row in summary:
        _budget = bmap.get(row.id, 0)
        if _budget <= 0:
            continue
        _spent = float(row.total or 0)
        _pct   = _spent / _budget * 100
        if _spent > _budget:
            alerts.append({'name': row.name, 'icon': row.icon,
                           'color': row.color, 'level': 'exceeded', 'pct': int(_pct)})
        elif _pct >= threshold:
            alerts.append({'name': row.name, 'icon': row.icon,
                           'color': row.color, 'level': 'warning', 'pct': int(_pct)})
    return {'budget_alerts': alerts}
```

- [ ] **Step 6: Запустить все тесты**

```
pytest tests/ -v --tb=short
```

Ожидание: все PASS

- [ ] **Step 7: Commit**

```
git add app.py
git commit -m "feat: update index and helper functions to support shared account context"
```

---

## Task 8: Обновить navbar в base.html

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Найти в base.html место с именем пользователя в navbar**

Открыть `templates/base.html`. Найти блок dropdown с именем пользователя (ищи `current_user.username` или `dropdown`).

- [ ] **Step 2: Добавить контекст-свитчер и shared-banner**

Внутри dropdown пользователя добавить пункты переключения счёта:

```html
<!-- Переключатель контекста — добавить перед существующими пунктами меню -->
<li><hr class="dropdown-divider"></li>
<li>
  <a class="dropdown-item {% if not active_shared_account %}fw-bold{% endif %}"
     href="{{ url_for('shared_switch_personal') }}">
    <i class="bi bi-person me-1"></i> Личный счёт
    {% if not active_shared_account %}<i class="bi bi-check2 ms-1 text-success"></i>{% endif %}
  </a>
</li>
{% for sa in user_shared_accounts %}
<li>
  <a class="dropdown-item {% if active_shared_account and active_shared_account.id == sa.id %}fw-bold{% endif %}"
     href="{{ url_for('shared_switch', shared_id=sa.id) }}">
    <i class="bi bi-people me-1"></i> {{ sa.name }}
    {% if active_shared_account and active_shared_account.id == sa.id %}
    <i class="bi bi-check2 ms-1 text-success"></i>
    {% endif %}
  </a>
</li>
{% endfor %}
<li>
  <a class="dropdown-item text-primary"
     href="{{ url_for('shared_create') }}">
    <i class="bi bi-plus-circle me-1"></i> Создать общий счёт
  </a>
</li>
<li><hr class="dropdown-divider"></li>
```

- [ ] **Step 3: Добавить shared-banner прямо после открывающего тега `<body>` или в начале `<main>`**

```html
{% if active_shared_account %}
<div class="alert alert-info alert-dismissible d-flex align-items-center mb-0 rounded-0 py-2" role="alert">
  <i class="bi bi-people-fill me-2"></i>
  <strong>Общий счёт: {{ active_shared_account.name }}</strong>
  <a href="{{ url_for('shared_manage', shared_id=active_shared_account.id) }}"
     class="ms-2 small">управление</a>
  <a href="{{ url_for('shared_switch_personal') }}"
     class="ms-auto btn btn-sm btn-outline-secondary">Вернуться в личный</a>
  <button type="button" class="btn-close ms-2" data-bs-dismiss="alert"></button>
</div>
{% endif %}
```

- [ ] **Step 4: Запустить все тесты**

```
pytest tests/ -v --tb=short
```

Ожидание: все PASS (изменения шаблона не ломают тесты)

- [ ] **Step 5: Commit**

```
git add templates/base.html
git commit -m "feat: add shared account context switcher and banner to navbar"
```

---

## Task 9: Бейдж "Добавил" в шаблонах списков + бюджетные маршруты

**Files:**
- Modify: `templates/expenses/list.html` — добавить бейдж `added_by`
- Modify: `templates/income/list.html` — добавить бейдж `added_by`
- Modify: `app.py` — найти маршрут бюджета и обновить для контекста

- [ ] **Step 1: Добавить бейдж "добавил" в templates/expenses/list.html**

Найти в `templates/expenses/list.html` цикл по расходам (ищи `{% for exp in expenses %}`). В строке с суммой/описанием расхода добавить рядом:

```html
{% if exp.added_by %}
<span class="badge bg-secondary ms-1" title="Добавил">
  {{ exp.added_by.avatar or '👤' }} {{ exp.added_by.username }}
</span>
{% endif %}
```

- [ ] **Step 2: Добавить бейдж "добавил" в templates/income/list.html**

Аналогично в `templates/income/list.html` в цикле `{% for inc in incomes %}`:

```html
{% if inc.added_by %}
<span class="badge bg-secondary ms-1" title="Добавил">
  {{ inc.added_by.avatar or '👤' }} {{ inc.added_by.username }}
</span>
{% endif %}
```

- [ ] **Step 3: Найти маршрут бюджета и обновить для контекста**

Выполнить поиск маршрута budget в app.py:
```
grep -n "route.*budget\|budget.*route\|MonthlyBudget" app.py | head -30
```

Найти POST-обработку создания/обновления бюджета. Добавить перед созданием `MonthlyBudget(...)`:

```python
ctx_type, ctx_id = get_active_context()
```

В объект `MonthlyBudget(...)` добавить:
```python
shared_account_id = ctx_id if ctx_type == 'shared' else None,
```

При этом `user_id` в shared-контексте должен оставаться `current_user.id` (для аудита).

Для фильтрации GET-запроса бюджета использовать:
```python
ctx_type, ctx_id = get_active_context()
if ctx_type == 'shared':
    budgets = MonthlyBudget.query.filter_by(
        shared_account_id=ctx_id, year=year, month=month
    ).all()
else:
    budgets = MonthlyBudget.query.filter(
        MonthlyBudget.user_id == ctx_id,
        MonthlyBudget.shared_account_id.is_(None),
        MonthlyBudget.year == year,
        MonthlyBudget.month == month,
    ).all()
```

- [ ] **Step 4: Запустить все тесты**

```
pytest tests/ -v --tb=short
```

Ожидание: все PASS

- [ ] **Step 5: Commit**

```
git add app.py templates/expenses/list.html templates/income/list.html
git commit -m "feat: add added_by badge to expense/income lists and update budget routes for context"
```

---

## Task 10: Итоговая проверка

- [ ] **Step 1: Запустить полный набор тестов**

```
pytest tests/ -v
```

Ожидание: все тесты PASS

- [ ] **Step 2: Проверить что существующие тесты не сломались**

```
pytest tests/ -v --tb=long 2>&1 | findstr /R "PASSED FAILED ERROR"
```

Ожидание: ни одного FAILED или ERROR

- [ ] **Step 3: Final commit**

```
git add -A
git commit -m "feat: shared accounts — complete implementation with context switching, expense/income/budget/index updates and added_by badges"
```
