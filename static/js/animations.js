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
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
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
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
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
