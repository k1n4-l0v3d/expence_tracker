from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort, session
from urllib.parse import urlparse, urljoin
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         login_required, current_user)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from datetime import date, datetime, timedelta, timezone
from sqlalchemy import extract, func
from functools import wraps
import os
import random
import re
import threading


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
            now = datetime.now(timezone.utc)
            if blocked_until and now < blocked_until:
                remaining = int((blocked_until - now).total_seconds() // 60) + 1
                return True, remaining
            return False, 0

    def record_failure(self, ip: str) -> None:
        with self._lock:
            entry = self._data.setdefault(ip, {"count": 0, "blocked_until": None})
            entry["count"] += 1
            if entry["count"] >= self.max_attempts:
                entry["blocked_until"] = datetime.now(timezone.utc) + timedelta(minutes=self.block_minutes)

    def reset(self, ip: str) -> None:
        with self._lock:
            self._data.pop(ip, None)


rate_limiter = RateLimiter()


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


load_dotenv()

app = Flask(__name__)
flask_app = app  # alias for tests


def is_safe_url(target):
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret')

db           = SQLAlchemy(app)
csrf         = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view     = 'login'
login_manager.login_message  = 'Войдите, чтобы продолжить.'
login_manager.login_message_category = 'warning'


# ─── Модели ───────────────────────────────────────────────────────────────────

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(64),  nullable=False, unique=True)
    email         = db.Column(db.String(120), nullable=False, unique=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role          = db.Column(db.String(10),  nullable=False, default='user')   # 'admin' | 'user'
    status        = db.Column(db.String(10),  nullable=False, default='active') # 'active' | 'warned' | 'banned'
    warning_count = db.Column(db.Integer, nullable=False, default=0)
    warning_note  = db.Column(db.Text)
    ban_reason    = db.Column(db.Text)
    avatar        = db.Column(db.String(10), nullable=True)
    salary_day    = db.Column(db.Integer, nullable=True)
    advance_day   = db.Column(db.Integer, nullable=True)
    created_at    = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_seen     = db.Column(db.DateTime)

    expenses = db.relationship('Expense',       backref='user', lazy='dynamic')
    incomes  = db.relationship('Income',        backref='user', lazy='dynamic')
    budgets  = db.relationship('MonthlyBudget', backref='user', lazy='dynamic')

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return self.role == 'admin'

    @property
    def is_banned(self) -> bool:
        return self.status == 'banned'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Category(db.Model):
    __tablename__ = 'categories'

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    color       = db.Column(db.String(7), nullable=False, default='#6c757d')
    icon        = db.Column(db.String(50), default='bi-wallet2')
    is_active   = db.Column(db.Boolean, nullable=False, default=True)
    created_at  = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    expenses = db.relationship('Expense',       backref='category', lazy=True)
    budgets  = db.relationship('MonthlyBudget', backref='category', lazy=True)
    user     = db.relationship('User', backref=db.backref('custom_categories', lazy='dynamic'))


class MonthlyBudget(db.Model):
    __tablename__ = 'monthly_budgets'

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    year        = db.Column(db.SmallInteger, nullable=False)
    month       = db.Column(db.SmallInteger, nullable=False)
    amount      = db.Column(db.Numeric(12, 2), nullable=False)

    __table_args__ = (db.UniqueConstraint('user_id', 'category_id', 'year', 'month'),)


class Income(db.Model):
    __tablename__ = 'incomes'

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount      = db.Column(db.Numeric(12, 2), nullable=False)
    source      = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))
    income_date = db.Column(db.Date, nullable=False, default=date.today)
    notes       = db.Column(db.Text)
    created_at  = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Expense(db.Model):
    __tablename__ = 'expenses'

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category_id  = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    amount       = db.Column(db.Numeric(12, 2), nullable=False)
    description  = db.Column(db.String(255))
    expense_date = db.Column(db.Date, nullable=False, default=date.today)
    is_planned   = db.Column(db.Boolean, nullable=False, default=True)
    notes        = db.Column(db.Text)
    created_at   = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, nullable=False, default=datetime.utcnow,
                             onupdate=datetime.utcnow)


# ─── Декораторы ───────────────────────────────────────────────────────────────

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def ban_check(f):
    """Блокируем забаненных пользователей на всех страницах приложения."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.is_authenticated and current_user.is_banned:
            logout_user()
            flash('Ваш аккаунт заблокирован.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


@app.before_request
def update_last_seen():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        db.session.commit()


# ─── Хелперы ──────────────────────────────────────────────────────────────────

def get_monthly_income(user_id: int, year: int, month: int) -> float:
    total = db.session.query(func.coalesce(func.sum(Income.amount), 0)).filter(
        Income.user_id == user_id,
        extract('year',  Income.income_date) == year,
        extract('month', Income.income_date) == month,
    ).scalar()
    return float(total)


def get_monthly_summary(user_id: int, year: int, month: int):
    rows = (
        db.session.query(
            Category.id,
            Category.name,
            Category.color,
            Category.icon,
            func.coalesce(func.sum(Expense.amount), 0).label('total'),
        )
        .outerjoin(
            Expense,
            (Expense.category_id == Category.id)
            & (Expense.user_id == user_id)
            & (extract('year',  Expense.expense_date) == year)
            & (extract('month', Expense.expense_date) == month),
        )
        .filter(
            Category.is_active.is_(True),
            db.or_(Category.user_id.is_(None), Category.user_id == user_id)
        )
        .group_by(Category.id, Category.name, Category.color, Category.icon)
        .order_by(func.coalesce(func.sum(Expense.amount), 0).desc())
        .all()
    )
    return rows


def get_budget_map(user_id: int, year: int, month: int) -> dict:
    budgets = MonthlyBudget.query.filter_by(user_id=user_id, year=year, month=month).all()
    return {b.category_id: float(b.amount) for b in budgets}


def months_list():
    return [(m, datetime(2000, m, 1).strftime('%B')) for m in range(1, 13)]


def _last_day_of_month(d: date) -> date:
    next_month = d.replace(day=28) + timedelta(days=4)
    return next_month.replace(day=1) - timedelta(days=1)


def next_payment_date(day: int) -> date:
    today = date.today()
    last = _last_day_of_month(today)
    clamped_day = min(day, last.day)
    candidate = today.replace(day=clamped_day)
    if candidate <= today:
        first_next = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        last_next = _last_day_of_month(first_next)
        candidate = first_next.replace(day=min(day, last_next.day))
    return candidate


def get_daily_budget_info(balance: float, salary_day, advance_day):
    options = []
    if salary_day:
        options.append((next_payment_date(salary_day), 'зарплаты'))
    if advance_day:
        options.append((next_payment_date(advance_day), 'аванса'))
    if not options:
        return None
    nearest_date, payment_type = min(options, key=lambda x: x[0])
    today = date.today()
    days_left = max((nearest_date - today).days, 1)
    return {
        'daily': round(balance / days_left, 2),
        'days_left': days_left,
        'payment_type': payment_type,
        'nearest_date': nearest_date,
    }


# ─── Авторизация ──────────────────────────────────────────────────────────────

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


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'GET':
        return render_template('auth/login.html')

    # ── POST ──────────────────────────────────────────────────────────
    ip = get_client_ip()

    # 1. Honeypot
    if request.form.get('website', ''):
        return render_template('auth/login.html')

    # 2. Rate limit
    blocked, minutes = rate_limiter.is_blocked(ip)
    if blocked:
        flash(f'Слишком много попыток. Попробуйте через {minutes} мин.', 'danger')
        return render_template('auth/login.html')

    # 3. Auth logic
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

    return render_template('auth/login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('login'))


# ─── Личный кабинет ───────────────────────────────────────────────────────────

@app.route('/profile')
@login_required
@ban_check
def profile():
    today = date.today()
    total_expenses = db.session.query(func.coalesce(func.sum(Expense.amount), 0))\
        .filter(Expense.user_id == current_user.id).scalar()
    total_income = db.session.query(func.coalesce(func.sum(Income.amount), 0))\
        .filter(Income.user_id == current_user.id).scalar()
    expense_count = Expense.query.filter_by(user_id=current_user.id).count()
    income_count  = Income.query.filter_by(user_id=current_user.id).count()
    return render_template('profile.html',
                           total_expenses=float(total_expenses),
                           total_income=float(total_income),
                           expense_count=expense_count,
                           income_count=income_count,
                           today=today)


@app.route('/profile/change-password', methods=['POST'])
@login_required
def change_password():
    old = request.form['old_password']
    new = request.form['new_password']
    confirm = request.form['confirm']
    if not current_user.check_password(old):
        flash('Старый пароль неверен.', 'danger')
    elif new != confirm:
        flash('Новые пароли не совпадают.', 'danger')
    elif len(new) < 6:
        flash('Пароль должен быть не менее 6 символов.', 'danger')
    else:
        current_user.set_password(new)
        db.session.commit()
        flash('Пароль изменён.', 'success')
    return redirect(url_for('profile'))


@app.route('/profile/avatar', methods=['POST'])
@login_required
def change_avatar():
    ALLOWED = {
        '😊','😎','🤓','🥳','😄','😇','🦊','🐱','🐶','🐸',
        '🦁','🐼','🐨','🦄','🐯','🦅','🦋','🌟','🎮','🎯',
        '🎸','🚀','⚡','🌙','🔥','💎','🍀','👾','🎃','🌈',
    }
    emoji = request.form.get('avatar', '').strip()
    if emoji not in ALLOWED:
        flash('Недопустимая аватарка.', 'danger')
        return redirect(url_for('profile'))
    current_user.avatar = emoji
    db.session.commit()
    flash('Аватарка обновлена!', 'success')
    return redirect(url_for('profile'))


# ─── Администраторская панель ──────────────────────────────────────────────────

@app.route('/admin')
@login_required
@admin_required
def admin_panel():
    users = User.query.order_by(User.created_at.desc()).all()
    # Статистика по каждому пользователю
    stats = {}
    for u in users:
        stats[u.id] = {
            'expenses': Expense.query.filter_by(user_id=u.id).count(),
            'incomes':  Income.query.filter_by(user_id=u.id).count(),
        }
    return render_template('admin/panel.html', users=users, stats=stats)


@app.route('/admin/user/<int:user_id>/warn', methods=['POST'])
@login_required
@admin_required
def admin_warn(user_id):
    user = db.session.get(User, user_id)
    if not user or user.is_admin:
        abort(400)
    note = request.form.get('note', '').strip()
    user.warning_count += 1
    user.warning_note   = note or None
    user.status         = 'warned'
    db.session.commit()
    flash(f'Пользователю {user.username} выдано предупреждение ({user.warning_count}).', 'warning')
    return redirect(url_for('admin_panel'))


@app.route('/admin/user/<int:user_id>/ban', methods=['POST'])
@login_required
@admin_required
def admin_ban(user_id):
    user = db.session.get(User, user_id)
    if not user or user.is_admin:
        abort(400)
    reason = request.form.get('reason', '').strip()
    user.status     = 'banned'
    user.ban_reason = reason or None
    db.session.commit()
    flash(f'Пользователь {user.username} заблокирован.', 'danger')
    return redirect(url_for('admin_panel'))


@app.route('/admin/user/<int:user_id>/unban', methods=['POST'])
@login_required
@admin_required
def admin_unban(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    user.status         = 'active'
    user.ban_reason     = None
    user.warning_count  = 0
    user.warning_note   = None
    db.session.commit()
    flash(f'Пользователь {user.username} разблокирован.', 'success')
    return redirect(url_for('admin_panel'))


@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    user = db.session.get(User, user_id)
    if not user or user.is_admin:
        abort(400)
    Expense.query.filter_by(user_id=user_id).delete()
    Income.query.filter_by(user_id=user_id).delete()
    MonthlyBudget.query.filter_by(user_id=user_id).delete()
    db.session.delete(user)
    db.session.commit()
    flash(f'Пользователь удалён.', 'warning')
    return redirect(url_for('admin_panel'))


# ─── Основные маршруты ────────────────────────────────────────────────────────

@app.route('/')
@login_required
@ban_check
def index():
    today = date.today()
    year  = int(request.args.get('year',  today.year))
    month = int(request.args.get('month', today.month))

    uid          = current_user.id
    summary      = get_monthly_summary(uid, year, month)
    budget_map   = get_budget_map(uid, year, month)
    total_spent  = sum(float(r.total) for r in summary)
    total_income = get_monthly_income(uid, year, month)
    balance      = total_income - total_spent

    daily_info = get_daily_budget_info(
        balance=balance,
        salary_day=current_user.salary_day,
        advance_day=current_user.advance_day,
    )

    recent = (
        Expense.query
        .filter(
            Expense.user_id == uid,
            extract('year',  Expense.expense_date) == year,
            extract('month', Expense.expense_date) == month,
        )
        .order_by(Expense.expense_date.desc(), Expense.created_at.desc())
        .limit(5).all()
    )

    return render_template('index.html',
        summary=summary, budget_map=budget_map,
        total_spent=total_spent, total_income=total_income, balance=balance,
        recent=recent, year=year, month=month, today=today, months=months_list(),
        daily_info=daily_info,
        salary_day=current_user.salary_day,
        advance_day=current_user.advance_day,
    )


@app.route('/expenses')
@login_required
@ban_check
def expenses_list():
    today  = date.today()
    year   = int(request.args.get('year',  today.year))
    month  = int(request.args.get('month', today.month))
    cat_id = request.args.get('category_id', type=int)
    uid    = current_user.id

    query = Expense.query.filter(
        Expense.user_id == uid,
        extract('year',  Expense.expense_date) == year,
        extract('month', Expense.expense_date) == month,
    )
    if cat_id:
        query = query.filter(Expense.category_id == cat_id)

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

    expenses   = query.all()
    categories = Category.query.filter(
        Category.is_active.is_(True),
        db.or_(Category.user_id.is_(None), Category.user_id == current_user.id)
    ).order_by(Category.name).all()

    return render_template('expenses/list.html',
        expenses=expenses, categories=categories,
        year=year, month=month, months=months_list(), selected_cat=cat_id, sort=sort)


@app.route('/expenses/add', methods=['GET', 'POST'])
@login_required
@ban_check
def expense_add():
    categories = Category.query.filter(
        Category.is_active.is_(True),
        db.or_(Category.user_id.is_(None), Category.user_id == current_user.id)
    ).order_by(Category.name).all()
    if request.method == 'POST':
        try:
            exp = Expense(
                user_id      = current_user.id,
                category_id  = int(request.form['category_id']),
                amount       = float(request.form['amount']),
                description  = request.form.get('description', '').strip() or None,
                expense_date = datetime.strptime(request.form['expense_date'], '%Y-%m-%d').date(),
                is_planned   = request.form.get('is_planned') == 'on',
                notes        = request.form.get('notes', '').strip() or None,
            )
            db.session.add(exp)
            db.session.commit()
            flash('Расход добавлен!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка: {e}', 'danger')
    return render_template('expenses/form.html', categories=categories,
                           expense=None, today=date.today())


@app.route('/expenses/<int:exp_id>/edit', methods=['GET', 'POST'])
@login_required
@ban_check
def expense_edit(exp_id):
    exp = Expense.query.filter_by(id=exp_id, user_id=current_user.id).first_or_404()
    categories = Category.query.filter(
        Category.is_active.is_(True),
        db.or_(Category.user_id.is_(None), Category.user_id == current_user.id)
    ).order_by(Category.name).all()
    if request.method == 'POST':
        try:
            exp.category_id  = int(request.form['category_id'])
            exp.amount       = float(request.form['amount'])
            exp.description  = request.form.get('description', '').strip() or None
            exp.expense_date = datetime.strptime(request.form['expense_date'], '%Y-%m-%d').date()
            exp.is_planned   = request.form.get('is_planned') == 'on'
            exp.notes        = request.form.get('notes', '').strip() or None
            db.session.commit()
            flash('Расход обновлён!', 'success')
            return redirect(url_for('expenses_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка: {e}', 'danger')
    return render_template('expenses/form.html', categories=categories,
                           expense=exp, today=date.today())


@app.route('/expenses/<int:exp_id>/delete', methods=['POST'])
@login_required
def expense_delete(exp_id):
    exp = Expense.query.filter_by(id=exp_id, user_id=current_user.id).first_or_404()
    db.session.delete(exp)
    db.session.commit()
    flash('Расход удалён.', 'warning')
    return redirect(url_for('expenses_list'))


@app.route('/categories/add', methods=['POST'])
@login_required
@ban_check
def category_add():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400
    name  = (data.get('name') or '').strip()
    color = data.get('color', '#6c757d')
    if color and not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        return jsonify({'error': 'Неверный формат цвета'}), 400

    if not name:
        return jsonify({'error': 'Название обязательно'}), 400
    if len(name) > 100:
        return jsonify({'error': 'Название слишком длинное'}), 400

    # Проверка: нет ли уже такой категории (системной или своей)
    existing = Category.query.filter(
        db.func.lower(Category.name) == name.lower(),
        db.or_(Category.user_id.is_(None), Category.user_id == current_user.id)
    ).first()
    if existing:
        return jsonify({'error': f'Категория «{existing.name}» уже существует'}), 409

    cat = Category(name=name, color=color, user_id=current_user.id)
    try:
        db.session.add(cat)
        db.session.commit()
        return jsonify({'id': cat.id, 'name': cat.name, 'color': cat.color}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Ошибка сервера'}), 500


@app.route('/budget', methods=['GET', 'POST'])
@login_required
@ban_check
def budget():
    today      = date.today()
    year       = int(request.args.get('year',  today.year))
    month      = int(request.args.get('month', today.month))
    uid        = current_user.id
    categories = Category.query.filter(
        Category.is_active.is_(True),
        db.or_(Category.user_id.is_(None), Category.user_id == current_user.id)
    ).order_by(Category.name).all()
    budget_map = get_budget_map(uid, year, month)

    if request.method == 'POST':
        year  = int(request.form['year'])
        month = int(request.form['month'])
        for cat in categories:
            val = request.form.get(f'budget_{cat.id}', '').strip()
            existing = MonthlyBudget.query.filter_by(
                user_id=uid, category_id=cat.id, year=year, month=month
            ).first()
            if val:
                amount = float(val)
                if existing:
                    existing.amount = amount
                else:
                    db.session.add(MonthlyBudget(
                        user_id=uid, category_id=cat.id,
                        year=year, month=month, amount=amount
                    ))
            elif existing:
                db.session.delete(existing)
        db.session.commit()
        flash('Бюджет сохранён!', 'success')
        return redirect(url_for('budget', year=year, month=month))

    return render_template('budget.html', categories=categories,
                           budget_map=budget_map, year=year, month=month,
                           months=months_list())


# ─── Доходы ───────────────────────────────────────────────────────────────────

@app.route('/income')
@login_required
@ban_check
def income_list():
    today = date.today()
    year  = int(request.args.get('year',  today.year))
    month = int(request.args.get('month', today.month))
    uid   = current_user.id

    incomes = (
        Income.query
        .filter(
            Income.user_id == uid,
            extract('year',  Income.income_date) == year,
            extract('month', Income.income_date) == month,
        )
        .order_by(Income.income_date.desc(), Income.created_at.desc()).all()
    )
    total = sum(float(i.amount) for i in incomes)
    return render_template('income/list.html',
                           incomes=incomes, total=total,
                           year=year, month=month, months=months_list())


@app.route('/income/add', methods=['GET', 'POST'])
@login_required
@ban_check
def income_add():
    if request.method == 'POST':
        try:
            inc = Income(
                user_id     = current_user.id,
                amount      = float(request.form['amount']),
                source      = request.form['source'].strip(),
                description = request.form.get('description', '').strip() or None,
                income_date = datetime.strptime(request.form['income_date'], '%Y-%m-%d').date(),
                notes       = request.form.get('notes', '').strip() or None,
            )
            db.session.add(inc)
            db.session.commit()
            flash('Доход добавлен!', 'success')
            return redirect(url_for('income_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка: {e}', 'danger')
    return render_template('income/form.html', income=None, today=date.today())


@app.route('/income/<int:inc_id>/edit', methods=['GET', 'POST'])
@login_required
@ban_check
def income_edit(inc_id):
    inc = Income.query.filter_by(id=inc_id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        try:
            inc.amount      = float(request.form['amount'])
            inc.source      = request.form['source'].strip()
            inc.description = request.form.get('description', '').strip() or None
            inc.income_date = datetime.strptime(request.form['income_date'], '%Y-%m-%d').date()
            inc.notes       = request.form.get('notes', '').strip() or None
            db.session.commit()
            flash('Доход обновлён!', 'success')
            return redirect(url_for('income_list'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка: {e}', 'danger')
    return render_template('income/form.html', income=inc, today=date.today())


@app.route('/income/<int:inc_id>/delete', methods=['POST'])
@login_required
def income_delete(inc_id):
    inc = Income.query.filter_by(id=inc_id, user_id=current_user.id).first_or_404()
    db.session.delete(inc)
    db.session.commit()
    flash('Доход удалён.', 'warning')
    return redirect(url_for('income_list'))


# ─── API ──────────────────────────────────────────────────────────────────────

@app.route('/api/chart-data')
@login_required
def chart_data():
    today = date.today()
    year  = int(request.args.get('year',  today.year))
    month = int(request.args.get('month', today.month))
    rows  = get_monthly_summary(current_user.id, year, month)
    return jsonify({
        'labels': [r.name for r in rows if float(r.total) > 0],
        'data':   [float(r.total) for r in rows if float(r.total) > 0],
        'colors': [r.color for r in rows if float(r.total) > 0],
    })


def _prev_period(year: int, month: int, mode: str):
    """Возвращает (year, month) периода для сравнения."""
    if mode == 'prev_year':
        return year - 1, month
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _month_label(year: int, month: int) -> str:
    MONTHS_RU = [
        '', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
        'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
    ]
    return f'{MONTHS_RU[month]} {year}'


@app.route('/api/stats-data')
@login_required
def stats_data():
    today = date.today()
    year  = int(request.args.get('year',  today.year))
    month = int(request.args.get('month', today.month))
    mode  = request.args.get('mode', 'prev_month')  # 'prev_month' | 'prev_year'
    uid   = current_user.id

    # ── Блок сравнения ────────────────────────────────────────────────
    py, pm = _prev_period(year, month, mode)

    def cat_totals(y, m):
        rows = (
            db.session.query(
                Category.id,
                Category.name,
                Category.color,
                Category.icon,
                func.coalesce(func.sum(Expense.amount), 0).label('total'),
            )
            .outerjoin(
                Expense,
                (Expense.category_id == Category.id)
                & (Expense.user_id == uid)
                & (extract('year',  Expense.expense_date) == y)
                & (extract('month', Expense.expense_date) == m),
            )
            .filter(
                Category.is_active.is_(True),
                db.or_(Category.user_id.is_(None), Category.user_id == uid)
            )
            .group_by(Category.id, Category.name, Category.color, Category.icon)
            .all()
        )
        return {r.id: {'name': r.name, 'color': r.color, 'icon': r.icon, 'total': float(r.total)} for r in rows}

    cur_map  = cat_totals(year, month)
    prev_map = cat_totals(py, pm)

    categories = []
    for cat_id, cur in cur_map.items():
        prev_total = prev_map.get(cat_id, {}).get('total', None)
        if cur['total'] == 0 and (prev_total is None or prev_total == 0):
            continue
        if prev_total is None or prev_total == 0:
            delta_pct = None  # новая категория
        else:
            delta_pct = round((cur['total'] - prev_total) / prev_total * 100, 1)
        categories.append({
            'id':        cat_id,
            'name':      cur['name'],
            'color':     cur['color'],
            'icon':      cur['icon'],
            'current':   cur['total'],
            'previous':  prev_total or 0,
            'delta_pct': delta_pct,
        })

    categories.sort(key=lambda x: x['current'], reverse=True)

    total_cur  = sum(c['current']  for c in categories)
    total_prev = sum(c['previous'] for c in categories)
    total_delta = round((total_cur - total_prev) / total_prev * 100, 1) if total_prev else None

    # ── Динамика за 3 месяца ─────────────────────────────────────────
    months_data = []
    cy, cm = year, month
    for _ in range(3):
        inc = float(db.session.query(
            func.coalesce(func.sum(Income.amount), 0)
        ).filter(
            Income.user_id == uid,
            extract('year',  Income.income_date) == cy,
            extract('month', Income.income_date) == cm,
        ).scalar())
        exp = float(db.session.query(
            func.coalesce(func.sum(Expense.amount), 0)
        ).filter(
            Expense.user_id == uid,
            extract('year',  Expense.expense_date) == cy,
            extract('month', Expense.expense_date) == cm,
        ).scalar())
        months_data.append({
            'year': cy, 'month': cm,
            'label': _month_label(cy, cm),
            'income': inc, 'expenses': exp,
            'balance': round(inc - exp, 2),
            'is_current': (cy == year and cm == month),
        })
        cy, cm = _prev_period(cy, cm, 'prev_month')

    months_data.reverse()  # хронологический порядок: старый → новый

    # % изменения относительно предыдущего месяца
    for i in range(1, len(months_data)):
        prev = months_data[i - 1]
        cur  = months_data[i]
        cur['income_delta']  = round((cur['income']   - prev['income'])   / prev['income']   * 100, 1) if prev['income']   else None
        cur['expense_delta'] = round((cur['expenses'] - prev['expenses']) / prev['expenses'] * 100, 1) if prev['expenses'] else None

    best_income   = max(months_data, key=lambda x: x['income'])
    worst_expense = max(months_data, key=lambda x: x['expenses'])
    best_balance  = max(months_data, key=lambda x: x['balance'])

    return jsonify({
        'comparison': {
            'mode':           mode,
            'current_label':  _month_label(year, month),
            'compare_label':  _month_label(py, pm),
            'categories':     categories,
            'total_current':  round(total_cur,  2),
            'total_previous': round(total_prev, 2),
            'total_delta':    total_delta,
        },
        'monthly': {
            'months':              months_data,
            'best_income_month':   {'label': best_income['label'],   'amount': best_income['income']},
            'worst_expense_month': {'label': worst_expense['label'], 'amount': worst_expense['expenses']},
            'best_balance_month':  {'label': best_balance['label'],  'amount': best_balance['balance']},
        },
    })


@app.route('/api/payment-days', methods=['POST'])
@login_required
def api_payment_days():
    def parse_day(val):
        if val is None or val == '':
            return None
        try:
            d = int(val)
        except (ValueError, TypeError):
            return -1
        return d if 1 <= d <= 31 else -1

    salary_day  = parse_day(request.form.get('salary_day'))
    advance_day = parse_day(request.form.get('advance_day'))

    if salary_day == -1 or advance_day == -1:
        return jsonify({'error': 'Значение должно быть от 1 до 31'}), 400

    current_user.salary_day  = salary_day
    current_user.advance_day = advance_day
    db.session.commit()
    return jsonify({'ok': True})


with app.app_context():
    db.create_all()
    # Добавляем новые колонки если их ещё нет (safe migration)
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    columns = [c['name'] for c in inspector.get_columns('users')]
    if 'avatar' not in columns:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN avatar VARCHAR(10) NULL;"))
            conn.commit()
    if 'salary_day' not in columns:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN salary_day INTEGER NULL;"))
            conn.commit()
    if 'advance_day' not in columns:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN advance_day INTEGER NULL;"))
            conn.commit()
    # Миграция categories: добавить user_id
    cat_columns = [c['name'] for c in inspector.get_columns('categories')]
    if 'user_id' not in cat_columns:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE categories ADD COLUMN user_id INTEGER NULL REFERENCES users(id);"))
            conn.commit()
    # Снять старый unique constraint на name
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE categories DROP CONSTRAINT IF EXISTS categories_name_key;"))
            conn.commit()
    except Exception as e:
        app.logger.warning("Could not drop categories_name_key constraint: %s", e)

if __name__ == '__main__':
    app.run(debug=False)
