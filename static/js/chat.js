(function () {
    'use strict';

    const STORAGE_KEY = 'chat_history';
    const STORAGE_MSGS = 'chat_messages';

    function loadHistory() {
        try { return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '[]'); } catch { return []; }
    }
    function saveHistory(h) {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(h.slice(-20)));
    }
    function loadMessages() {
        try { return JSON.parse(sessionStorage.getItem(STORAGE_MSGS) || '[]'); } catch { return []; }
    }
    function saveMessages(msgs) {
        sessionStorage.setItem(STORAGE_MSGS, JSON.stringify(msgs.slice(-40)));
    }

    const history = loadHistory();

    function csrf() {
        return document.querySelector('meta[name="csrf-token"]')?.content ?? '';
    }

    function buildWidget() {
        const btn = document.createElement('button');
        btn.id = 'chat-toggle';
        btn.title = 'ИИ-помощник';
        btn.innerHTML = '<i class="bi bi-robot"></i>';

        const popup = document.createElement('div');
        popup.id = 'chat-popup';
        popup.innerHTML = `
<div id="chat-header">
  <div class="chat-title">
    <i class="bi bi-robot"></i>
    <div>
      <div>ИИ-помощник</div>
      <div class="chat-status">● Groq / Llama3</div>
    </div>
  </div>
  <button id="chat-close" title="Закрыть"><i class="bi bi-x-lg"></i></button>
</div>
<div id="chat-messages"></div>
<div id="chat-input-area">
  <textarea id="chat-input" rows="1" placeholder="Напиши сообщение..."></textarea>
  <button id="chat-send" title="Отправить"><i class="bi bi-send-fill"></i></button>
</div>`;

        document.body.appendChild(btn);
        document.body.appendChild(popup);

        restoreMessages();

        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            popup.classList.toggle('open');
        });
        popup.addEventListener('click', (e) => e.stopPropagation());
        document.getElementById('chat-close').addEventListener('click', () => {
            popup.classList.remove('open');
        });
        document.addEventListener('click', () => popup.classList.remove('open'));

        const input   = document.getElementById('chat-input');
        const sendBtn = document.getElementById('chat-send');

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
        });
        input.addEventListener('input', () => {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 100) + 'px';
        });
        sendBtn.addEventListener('click', send);
    }

    function restoreMessages() {
        const saved = loadMessages();
        const msgs = document.getElementById('chat-messages');
        if (saved.length === 0) {
            const bubble = document.createElement('div');
            bubble.className = 'chat-bubble bot';
            bubble.innerHTML = 'Привет! Я помогу управлять финансами. Попробуй написать: <em>«добавь расход 500 рублей на кафе»</em>';
            msgs.appendChild(bubble);
        } else {
            saved.forEach(m => _renderBubble(m.text, m.role));
        }
        msgs.scrollTop = msgs.scrollHeight;
    }

    function _renderBubble(text, role) {
        const msgs   = document.getElementById('chat-messages');
        const bubble = document.createElement('div');
        bubble.className = 'chat-bubble ' + role;
        bubble.textContent = text;
        msgs.appendChild(bubble);
        return bubble;
    }

    function appendBubble(text, role) {
        const bubble = _renderBubble(text, role);
        document.getElementById('chat-messages').scrollTop = 99999;
        const saved = loadMessages();
        saved.push({ text, role });
        saveMessages(saved);
        return bubble;
    }

    function showTyping() {
        const msgs = document.getElementById('chat-messages');
        const el   = document.createElement('div');
        el.id        = 'chat-typing';
        el.className = 'chat-typing';
        el.innerHTML = '<span></span><span></span><span></span>';
        msgs.appendChild(el);
        msgs.scrollTop = msgs.scrollHeight;
    }

    function hideTyping() {
        document.getElementById('chat-typing')?.remove();
    }

    async function send() {
        const input   = document.getElementById('chat-input');
        const sendBtn = document.getElementById('chat-send');
        const text    = input.value.trim();
        if (!text) return;

        input.value = '';
        input.style.height = 'auto';
        sendBtn.disabled = true;

        appendBubble(text, 'user');
        history.push({ role: 'user', content: text });
        if (history.length > 20) history.splice(0, history.length - 20);
        saveHistory(history);

        showTyping();

        try {
            const res  = await fetch('/api/chat', {
                method:  'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken':  csrf(),
                },
                body: JSON.stringify({ message: text, history: history.slice(-10) }),
            });
            const data = await res.json();
            hideTyping();

            const role = data.ok ? 'bot' : 'error';
            appendBubble(data.message, role);

            if (data.ok) {
                history.push({ role: 'assistant', content: data.message });
                if (history.length > 20) history.splice(0, history.length - 20);
                saveHistory(history);
                if (data.reload) {
                    setTimeout(() => window.location.reload(), 1500);
                }
            }
        } catch {
            hideTyping();
            appendBubble('Ошибка соединения. Попробуй ещё раз.', 'error');
        } finally {
            sendBtn.disabled = false;
            input.focus();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', buildWidget);
    } else {
        buildWidget();
    }
})();
