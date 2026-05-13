# Чат общего счёта — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить чат на страницу управления общим счётом: сообщения хранятся в БД (макс. 50), обновляются polling-ом каждые 4 сек, поддерживаются реакции ❤️/👍 и удаление своих сообщений.

**Architecture:** Две новые SQLAlchemy-модели (`SharedAccountMessage`, `SharedAccountReaction`); 4 JSON API-маршрута в `app.py`; JS-блок в `templates/shared/manage.html` реализует polling, рендеринг пузырьков, реакции и отправку.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, Vanilla JS (fetch + setInterval), Bootstrap 5, pytest

---

## File Map

| Файл | Изменение |
|---|---|
| `app.py` | Добавить модели `SharedAccountMessage`, `SharedAccountReaction` и 4 API-маршрута |
| `templates/shared/manage.html` | Добавить блок чата + JS (polling, рендеринг, отправка, реакции) |
| `tests/conftest.py` | Добавить новые модели в `clean_db` |
| `tests/test_shared_chat.py` | Создать (все тесты чата) |
| `migrations/001_shared_accounts.sql` | Добавить 2 новые таблицы |

---

## Task 1: Модели SharedAccountMessage и SharedAccountReaction

**Files:**
- Modify: `app.py` — добавить модели после класса `SharedAccountInvitation`
- Modify: `tests/conftest.py` — добавить новые модели в `clean_db`
- Modify: `migrations/001_shared_accounts.sql` — SQL для прод-БД

- [ ] **Step 1: Написать failing тест**

Создать файл `tests/test_shared_chat.py`:

```python
import pytest
from app import app as flask_app, db


def create_user(username, email, password='pw123456'):
    from app import User
    u = User(username=username, email=email)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return u


def login(client, username, password='pw123456'):
    return client.post('/login', data={'username': username, 'password': password},
                       follow_redirects=True)


def make_shared(owner):
    from app import SharedAccount, SharedAccountMember
    sa = SharedAccount(name='Chat Test', created_by_user_id=owner.id)
    db.session.add(sa)
    db.session.flush()
    db.session.add(SharedAccountMember(shared_account_id=sa.id, user_id=owner.id))
    db.session.commit()
    return sa


def test_message_model_creation():
    from app import SharedAccountMessage, SharedAccountReaction
    with flask_app.app_context():
        u = create_user('m_owner', 'm_owner@test.com')
        sa = make_shared(u)
        msg = SharedAccountMessage(
            shared_account_id=sa.id, user_id=u.id, text='Hello'
        )
        db.session.add(msg)
        db.session.commit()
        assert SharedAccountMessage.query.count() == 1

        reaction = SharedAccountReaction(
            message_id=msg.id, user_id=u.id, emoji='❤️'
        )
        db.session.add(reaction)
        db.session.commit()
        assert SharedAccountReaction.query.count() == 1
```

- [ ] **Step 2: Запустить — убедиться FAIL**

```
pytest tests/test_shared_chat.py::test_message_model_creation -v
```

Ожидание: `ImportError: cannot import name 'SharedAccountMessage'`

- [ ] **Step 3: Добавить модели в app.py**

Найти конец класса `SharedAccountInvitation` (строка с последним `db.relationship`) и добавить после него:

```python
class SharedAccountMessage(db.Model):
    __tablename__ = 'shared_account_messages'

    id                = db.Column(db.Integer, primary_key=True)
    shared_account_id = db.Column(db.Integer,
                                  db.ForeignKey('shared_accounts.id', ondelete='CASCADE'),
                                  nullable=False)
    user_id           = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    text              = db.Column(db.String(1000), nullable=False)
    created_at        = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    shared_account = db.relationship('SharedAccount',
                                     backref=db.backref('messages', lazy='dynamic',
                                                        cascade='all, delete-orphan'))
    author    = db.relationship('User', foreign_keys=[user_id])
    reactions = db.relationship('SharedAccountReaction', backref='message',
                                lazy=True, cascade='all, delete-orphan')


class SharedAccountReaction(db.Model):
    __tablename__ = 'shared_account_reactions'

    id         = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer,
                           db.ForeignKey('shared_account_messages.id', ondelete='CASCADE'),
                           nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    emoji      = db.Column(db.String(5), nullable=False)

    __table_args__ = (db.UniqueConstraint('message_id', 'user_id', 'emoji'),)

    user = db.relationship('User', foreign_keys=[user_id])
```

- [ ] **Step 4: Обновить clean_db в tests/conftest.py**

Найти блок `clean_db`. Добавить удаление новых таблиц **перед** `SharedAccountMember` и `SharedAccount`:

```python
        from app import (User, Expense, Income, MonthlyBudget,
                         Category, ExpenseAttachment, SavingsAccount, Debt,
                         SharedAccountMember, SharedAccount, SharedAccountInvitation,
                         SharedAccountReaction, SharedAccountMessage)
        db.session.query(ExpenseAttachment).delete()
        db.session.query(MonthlyBudget).delete()
        db.session.query(Expense).delete()
        db.session.query(Income).delete()
        db.session.query(Category).delete()
        db.session.query(SavingsAccount).delete()
        db.session.query(Debt).delete()
        db.session.query(SharedAccountInvitation).delete()
        db.session.query(SharedAccountReaction).delete()
        db.session.query(SharedAccountMessage).delete()
        db.session.query(SharedAccountMember).delete()
        db.session.query(SharedAccount).delete()
        db.session.query(User).delete()
        db.session.commit()
```

- [ ] **Step 5: Добавить SQL-миграцию**

В конец файла `migrations/001_shared_accounts.sql` добавить:

```sql
CREATE TABLE IF NOT EXISTS shared_account_messages (
    id SERIAL PRIMARY KEY,
    shared_account_id INTEGER NOT NULL REFERENCES shared_accounts(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    text VARCHAR(1000) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS shared_account_reactions (
    id SERIAL PRIMARY KEY,
    message_id INTEGER NOT NULL REFERENCES shared_account_messages(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    emoji VARCHAR(5) NOT NULL,
    UNIQUE(message_id, user_id, emoji)
);
```

- [ ] **Step 6: Запустить тест — убедиться PASS**

```
pytest tests/test_shared_chat.py::test_message_model_creation -v
```

Ожидание: PASS

- [ ] **Step 7: Прогнать все тесты — нет регрессий**

```
pytest tests/ -q --tb=short
```

Ожидание: все предыдущие тесты PASS

- [ ] **Step 8: Commit**

```
git add app.py tests/conftest.py tests/test_shared_chat.py migrations/001_shared_accounts.sql
git commit -m "feat: add SharedAccountMessage and SharedAccountReaction models"
```

---

## Task 2: API-маршруты чата

**Files:**
- Modify: `app.py` — добавить хелпер `_require_shared_member` и 4 маршрута

- [ ] **Step 1: Написать failing тесты**

Добавить в `tests/test_shared_chat.py`:

```python
def test_send_and_get_message(client):
    from app import SharedAccountMessage
    with flask_app.app_context():
        u = create_user('send_u1', 'send_u1@test.com')
        sa = make_shared(u)
        sa_id = sa.id

    login(client, 'send_u1')
    resp = client.post(f'/api/shared/{sa_id}/messages',
                       data={'text': 'Купи молоко'})
    assert resp.status_code == 200
    assert resp.get_json()['ok'] is True

    resp = client.get(f'/api/shared/{sa_id}/messages')
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]['text'] == 'Купи молоко'
    assert data[0]['is_mine'] is True


def test_non_member_cannot_send(client):
    from app import SharedAccount, SharedAccountMember
    with flask_app.app_context():
        owner = create_user('nm_owner', 'nm_owner@test.com')
        create_user('nm_other', 'nm_other@test.com')
        sa = make_shared(owner)
        sa_id = sa.id

    login(client, 'nm_other')
    resp = client.post(f'/api/shared/{sa_id}/messages', data={'text': 'Hello'})
    assert resp.status_code == 403


def test_delete_own_message(client):
    from app import SharedAccountMessage
    with flask_app.app_context():
        u = create_user('del_u1', 'del_u1@test.com')
        sa = make_shared(u)
        msg = SharedAccountMessage(
            shared_account_id=sa.id, user_id=u.id, text='Delete me'
        )
        db.session.add(msg)
        db.session.commit()
        sa_id, msg_id = sa.id, msg.id

    login(client, 'del_u1')
    resp = client.delete(f'/api/shared/{sa_id}/messages/{msg_id}')
    assert resp.status_code == 200
    assert resp.get_json()['ok'] is True

    with flask_app.app_context():
        assert db.session.get(SharedAccountMessage, msg_id) is None


def test_cannot_delete_others_message(client):
    from app import SharedAccount, SharedAccountMember, SharedAccountMessage
    with flask_app.app_context():
        owner = create_user('prot_owner', 'prot_owner@test.com')
        other = create_user('prot_other', 'prot_other@test.com')
        sa = make_shared(owner)
        db.session.add(SharedAccountMember(
            shared_account_id=sa.id, user_id=other.id
        ))
        msg = SharedAccountMessage(
            shared_account_id=sa.id, user_id=owner.id, text='Protected'
        )
        db.session.add(msg)
        db.session.commit()
        sa_id, msg_id = sa.id, msg.id

    login(client, 'prot_other')
    resp = client.delete(f'/api/shared/{sa_id}/messages/{msg_id}')
    assert resp.status_code == 403


def test_react_toggle(client):
    from app import SharedAccountMessage, SharedAccountReaction
    with flask_app.app_context():
        u = create_user('react_u1', 'react_u1@test.com')
        sa = make_shared(u)
        msg = SharedAccountMessage(
            shared_account_id=sa.id, user_id=u.id, text='Hi'
        )
        db.session.add(msg)
        db.session.commit()
        sa_id, msg_id = sa.id, msg.id

    login(client, 'react_u1')
    resp = client.post(
        f'/api/shared/{sa_id}/messages/{msg_id}/react',
        data={'emoji': '❤️'}
    )
    assert resp.get_json()['action'] == 'added'

    resp = client.post(
        f'/api/shared/{sa_id}/messages/{msg_id}/react',
        data={'emoji': '❤️'}
    )
    assert resp.get_json()['action'] == 'removed'

    with flask_app.app_context():
        assert SharedAccountReaction.query.filter_by(message_id=msg_id).count() == 0


def test_max_50_messages_enforced(client):
    from app import SharedAccountMessage
    with flask_app.app_context():
        u = create_user('max_u1', 'max_u1@test.com')
        sa = make_shared(u)
        for i in range(50):
            db.session.add(SharedAccountMessage(
                shared_account_id=sa.id, user_id=u.id, text=f'msg {i}'
            ))
        db.session.commit()
        sa_id = sa.id

    login(client, 'max_u1')
    client.post(f'/api/shared/{sa_id}/messages', data={'text': 'msg 51'})

    with flask_app.app_context():
        count = SharedAccountMessage.query.filter_by(shared_account_id=sa_id).count()
        assert count == 50
        latest = (SharedAccountMessage.query
                  .filter_by(shared_account_id=sa_id)
                  .order_by(SharedAccountMessage.created_at.desc())
                  .first())
        assert latest.text == 'msg 51'
```

- [ ] **Step 2: Запустить — убедиться FAIL**

```
pytest tests/test_shared_chat.py::test_send_and_get_message -v
```

Ожидание: `404` (маршрут не существует)

- [ ] **Step 3: Добавить хелпер и 4 API-маршрута в app.py**

Найти раздел `# ─── API ───` в app.py. Добавить перед ним:

```python
# ─── Chat API helpers ─────────────────────────────────────────────────────────

def _require_shared_member(shared_id: int):
    """Abort 403 if current_user is not a member of shared_id."""
    m = SharedAccountMember.query.filter_by(
        shared_account_id=shared_id, user_id=current_user.id
    ).first()
    if not m:
        abort(403)


# ─── Shared chat API ──────────────────────────────────────────────────────────

@app.route('/api/shared/<int:shared_id>/messages')
@login_required
def api_chat_messages(shared_id):
    _require_shared_member(shared_id)
    msgs = (SharedAccountMessage.query
            .filter_by(shared_account_id=shared_id)
            .order_by(SharedAccountMessage.created_at.asc())
            .limit(50).all())
    result = []
    for m in msgs:
        reaction_counts = {}
        my_reactions = []
        for r in m.reactions:
            reaction_counts[r.emoji] = reaction_counts.get(r.emoji, 0) + 1
            if r.user_id == current_user.id:
                my_reactions.append(r.emoji)
        result.append({
            'id': m.id,
            'text': m.text,
            'created_at': m.created_at.strftime('%d.%m %H:%M'),
            'is_mine': m.user_id == current_user.id,
            'author': {
                'username': m.author.username,
                'avatar': m.author.avatar or '',
            },
            'reactions': reaction_counts,
            'my_reactions': my_reactions,
        })
    return jsonify(result)


@app.route('/api/shared/<int:shared_id>/messages', methods=['POST'])
@login_required
def api_chat_send(shared_id):
    _require_shared_member(shared_id)
    text = request.form.get('text', '').strip()
    if not text or len(text) > 1000:
        return jsonify({'error': 'Текст от 1 до 1000 символов'}), 400
    msg = SharedAccountMessage(
        shared_account_id=shared_id, user_id=current_user.id, text=text
    )
    db.session.add(msg)
    db.session.flush()
    count = SharedAccountMessage.query.filter_by(shared_account_id=shared_id).count()
    if count > 50:
        oldest = (SharedAccountMessage.query
                  .filter_by(shared_account_id=shared_id)
                  .order_by(SharedAccountMessage.created_at.asc())
                  .limit(count - 50).all())
        for old in oldest:
            db.session.delete(old)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/shared/<int:shared_id>/messages/<int:msg_id>', methods=['DELETE'])
@login_required
def api_chat_delete(shared_id, msg_id):
    _require_shared_member(shared_id)
    msg = SharedAccountMessage.query.filter_by(
        id=msg_id, shared_account_id=shared_id
    ).first_or_404()
    if msg.user_id != current_user.id:
        abort(403)
    db.session.delete(msg)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/shared/<int:shared_id>/messages/<int:msg_id>/react', methods=['POST'])
@login_required
def api_chat_react(shared_id, msg_id):
    _require_shared_member(shared_id)
    ALLOWED = {'❤️', '👍'}
    emoji = request.form.get('emoji', '').strip()
    if emoji not in ALLOWED:
        return jsonify({'error': 'Недопустимая реакция'}), 400
    SharedAccountMessage.query.filter_by(
        id=msg_id, shared_account_id=shared_id
    ).first_or_404()
    existing = SharedAccountReaction.query.filter_by(
        message_id=msg_id, user_id=current_user.id, emoji=emoji
    ).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'ok': True, 'action': 'removed'})
    db.session.add(SharedAccountReaction(
        message_id=msg_id, user_id=current_user.id, emoji=emoji
    ))
    db.session.commit()
    return jsonify({'ok': True, 'action': 'added'})
```

- [ ] **Step 4: Запустить тесты чата — убедиться PASS**

```
pytest tests/test_shared_chat.py -v --tb=short
```

Ожидание: все 7 тестов PASS

- [ ] **Step 5: Прогнать все тесты**

```
pytest tests/ -q --tb=short
```

Ожидание: все предыдущие тесты PASS

- [ ] **Step 6: Commit**

```
git add app.py tests/test_shared_chat.py
git commit -m "feat: add shared account chat API routes"
```

---

## Task 3: UI чата в manage.html

**Files:**
- Modify: `templates/shared/manage.html` — добавить блок чата + JS после блока участников/приглашения

- [ ] **Step 1: Добавить блок чата в manage.html**

В файле `templates/shared/manage.html` найти строку `{% endif %}` в конце (перед `</div>` контейнера) и **перед ней** вставить чат-блок и JS. Заменить:

```html
{% endif %}

</div>
{% endblock %}
```

на:

```html
  {# ── Чат ────────────────────────────────────────────────────── #}
  <div class="col-12 mt-2">
    <div class="card shadow-sm">
      <div class="card-header fw-semibold d-flex align-items-center gap-2">
        <i class="bi bi-chat-dots-fill text-primary"></i> Чат
      </div>
      <div class="card-body p-0">
        <div id="chatMessages"
             style="height:350px;overflow-y:auto;padding:1rem;scroll-behavior:smooth">
          <div class="text-center text-muted small py-5" id="chatEmpty">
            <i class="bi bi-chat-dots opacity-25" style="font-size:2rem"></i>
            <div class="mt-2">Нет сообщений. Напишите первым!</div>
          </div>
        </div>
        <div class="border-top d-flex gap-2 p-2">
          <input type="text" id="chatInput" class="form-control"
                 placeholder="Написать сообщение..." maxlength="1000"
                 autocomplete="off">
          <button class="btn btn-primary px-3" id="chatSend" title="Отправить">
            <i class="bi bi-send-fill"></i>
          </button>
        </div>
      </div>
    </div>
  </div>

{% endif %}

</div>

<script>
(function () {
    const SHARED_ID  = {{ account.id if account else 0 }};
    const CSRF_TOKEN = {{ csrf_token() | tojson }};
    const EMOJIS     = ['❤️', '👍'];

    if (!SHARED_ID) return;

    let lastId  = null;
    let sending = false;

    function esc(s) {
        return String(s)
            .replace(/&/g,'&amp;').replace(/</g,'&lt;')
            .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    function buildBubble(msg) {
        const reactions = EMOJIS.map(e => {
            const cnt    = msg.reactions[e] || 0;
            const active = msg.my_reactions.includes(e);
            return `<button class="chat-react-btn btn btn-sm"
                            data-mid="${msg.id}" data-emoji="${e}"
                            style="padding:1px 8px;font-size:.75rem;border-radius:12px;
                                   background:${active ? 'rgba(232,115,107,.15)' : 'transparent'};
                                   border:1px solid ${active ? 'var(--clr-primary-from)' : '#dee2e6'};
                                   color:inherit">
                        ${e}${cnt ? ' ' + cnt : ''}
                    </button>`;
        }).join('');

        if (msg.is_mine) {
            return `
            <div class="d-flex flex-column align-items-end mb-3" data-mid="${msg.id}">
                <div class="text-muted mb-1" style="font-size:.72rem">${esc(msg.created_at)}</div>
                <div class="d-flex align-items-end gap-1">
                    <button class="chat-del-btn btn btn-sm"
                            data-mid="${msg.id}"
                            style="opacity:.35;background:none;border:none;padding:2px 4px"
                            title="Удалить">
                        <i class="bi bi-trash3"></i>
                    </button>
                    <div class="px-3 py-2 rounded-3 text-white"
                         style="max-width:72%;word-break:break-word;
                                background:linear-gradient(135deg,var(--clr-primary-from),var(--clr-primary-to))">
                        ${esc(msg.text)}
                    </div>
                </div>
                <div class="d-flex gap-1 mt-1">${reactions}</div>
            </div>`;
        }
        const av = msg.author.avatar || '👤';
        return `
        <div class="d-flex flex-column align-items-start mb-3" data-mid="${msg.id}">
            <div class="text-muted mb-1" style="font-size:.72rem">
                ${esc(av)} ${esc(msg.author.username)} · ${esc(msg.created_at)}
            </div>
            <div class="px-3 py-2 rounded-3"
                 style="max-width:72%;word-break:break-word;background:var(--bs-secondary-bg)">
                ${esc(msg.text)}
            </div>
            <div class="d-flex gap-1 mt-1">${reactions}</div>
        </div>`;
    }

    function attachHandlers() {
        document.querySelectorAll('.chat-react-btn').forEach(btn => {
            btn.onclick = () => {
                const fd = new FormData();
                fd.append('emoji', btn.dataset.emoji);
                fetch(`/api/shared/${SHARED_ID}/messages/${btn.dataset.mid}/react`, {
                    method: 'POST',
                    headers: {'X-CSRFToken': CSRF_TOKEN},
                    body: fd,
                }).then(() => { lastId = null; load(); });
            };
        });

        document.querySelectorAll('.chat-del-btn').forEach(btn => {
            btn.onclick = () => {
                if (!confirm('Удалить сообщение?')) return;
                fetch(`/api/shared/${SHARED_ID}/messages/${btn.dataset.mid}`, {
                    method: 'DELETE',
                    headers: {'X-CSRFToken': CSRF_TOKEN},
                }).then(() => { lastId = null; load(); });
            };
        });
    }

    function load() {
        if (document.hidden) return;
        fetch(`/api/shared/${SHARED_ID}/messages`)
            .then(r => r.json())
            .then(msgs => {
                const newId = msgs.length ? msgs[msgs.length - 1].id : null;
                if (newId === lastId) return;

                const box    = document.getElementById('chatMessages');
                const atEnd  = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
                const empty  = document.getElementById('chatEmpty');

                if (!msgs.length) {
                    if (empty) empty.style.display = '';
                    return;
                }
                if (empty) empty.style.display = 'none';

                box.innerHTML = msgs.map(buildBubble).join('');
                lastId = newId;
                if (atEnd) box.scrollTop = box.scrollHeight;
                attachHandlers();
            })
            .catch(() => {});
    }

    function send() {
        if (sending) return;
        const input = document.getElementById('chatInput');
        const text  = input.value.trim();
        if (!text) return;
        sending = true;
        const fd = new FormData();
        fd.append('text', text);
        input.value = '';
        fetch(`/api/shared/${SHARED_ID}/messages`, {
            method: 'POST',
            headers: {'X-CSRFToken': CSRF_TOKEN},
            body: fd,
        }).then(() => { lastId = null; load(); })
          .finally(() => { sending = false; });
    }

    document.getElementById('chatSend').addEventListener('click', send);
    document.getElementById('chatInput').addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    });

    load();
    setInterval(load, 4000);
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) load();
    });
})();
</script>
{% endblock %}
```

- [ ] **Step 2: Проверить что страница рендерится без ошибок**

```
pytest tests/test_shared_chat.py -v --tb=short
```

Ожидание: все тесты PASS (шаблон компилируется)

- [ ] **Step 3: Убедиться нет регрессий**

```
pytest tests/ -q --tb=short
```

Ожидание: все предыдущие тесты PASS

- [ ] **Step 4: Commit**

```
git add templates/shared/manage.html
git commit -m "feat: add shared account chat UI with polling, bubbles and reactions"
```

---

## Task 4: Итоговая проверка

- [ ] **Step 1: Запустить полный набор тестов**

```
pytest tests/ -v --tb=short
```

Ожидание: все тесты PASS (кроме pre-existing `test_pdf_export`)

- [ ] **Step 2: Final commit**

```
git add -A
git commit -m "feat: shared account chat — complete implementation"
```
