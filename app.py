from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort, session, send_file, Response, stream_with_context
from urllib.parse import urlparse, urljoin
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         login_required, current_user)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
load_dotenv()  # must run before weasyprint import so DYLD_LIBRARY_PATH is set
from datetime import date, datetime, timedelta, timezone
from sqlalchemy import extract, func
from sqlalchemy.orm import joinedload
from functools import wraps
import os
import io
import json
import random
import calendar
import math
import re
import threading
import openpyxl
from groq import Groq
from openpyxl.styles import Font
try:
    import weasyprint
except Exception:
    weasyprint = None


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


app = Flask(__name__)
import logging
logging.basicConfig(level=logging.INFO)
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


@app.template_filter('fmt_rub')
def fmt_rub_filter(value, decimals=2):
    """Format a number with thousands separator (non-breaking space) and fixed decimals."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    formatted = f"{v:,.{decimals}f}"          # e.g. "100,000.00"
    return formatted.replace(",", " ")   # "100 000.00" (non-breaking space)
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
    salary_day        = db.Column(db.Integer, nullable=True)
    advance_day       = db.Column(db.Integer, nullable=True)
    budget_alert_pct  = db.Column(db.Integer, nullable=False, default=80)
    created_at        = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_seen     = db.Column(db.DateTime)

    expenses = db.relationship('Expense',       foreign_keys='[Expense.user_id]',
                               backref='user', lazy='dynamic')
    incomes  = db.relationship('Income',        foreign_keys='[Income.user_id]',
                               backref='user', lazy='dynamic')
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


class SavingsAccount(db.Model):
    __tablename__ = 'savings_accounts'

    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name          = db.Column(db.String(100), nullable=False)
    color         = db.Column(db.String(7),  nullable=False, default='#0d6efd')
    icon          = db.Column(db.String(50), nullable=False, default='bi-piggy-bank')
    target_amount = db.Column(db.Numeric(12, 2), nullable=True)
    is_active     = db.Column(db.Boolean, nullable=False, default=True)
    created_at    = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    image_data    = db.Column(db.LargeBinary, nullable=True)
    image_mime    = db.Column(db.String(50),  nullable=True)
    shared_account_id = db.Column(db.Integer, db.ForeignKey('shared_accounts.id'), nullable=True)

    user = db.relationship('User', backref=db.backref('savings_accounts', lazy='dynamic'))


class MonthlyBudget(db.Model):
    __tablename__ = 'monthly_budgets'

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    year        = db.Column(db.SmallInteger, nullable=False)
    month       = db.Column(db.SmallInteger, nullable=False)
    amount            = db.Column(db.Numeric(12, 2), nullable=False)
    shared_account_id = db.Column(db.Integer, db.ForeignKey('shared_accounts.id'), nullable=True)

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

    savings_account_id = db.Column(db.Integer, db.ForeignKey('savings_accounts.id'), nullable=True)
    savings_account    = db.relationship('SavingsAccount', foreign_keys=[savings_account_id])
    shared_account_id  = db.Column(db.Integer, db.ForeignKey('shared_accounts.id'), nullable=True)
    added_by_user_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    shared_account     = db.relationship('SharedAccount', foreign_keys=[shared_account_id],
                                         backref=db.backref('incomes', lazy='dynamic'))
    added_by           = db.relationship('User', foreign_keys=[added_by_user_id])


class Expense(db.Model):
    __tablename__ = 'expenses'

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category_id  = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    amount       = db.Column(db.Numeric(12, 2), nullable=False)
    description  = db.Column(db.String(255))
    expense_date = db.Column(db.Date, nullable=False, default=date.today)
    is_planned   = db.Column(db.Boolean, nullable=False, default=True)
    is_spent     = db.Column(db.Boolean, nullable=False, default=True)
    notes        = db.Column(db.Text)
    created_at   = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, nullable=False, default=datetime.utcnow,
                             onupdate=datetime.utcnow)

    savings_account_id = db.Column(db.Integer, db.ForeignKey('savings_accounts.id'), nullable=True)
    savings_account    = db.relationship('SavingsAccount', foreign_keys=[savings_account_id])
    shared_account_id  = db.Column(db.Integer, db.ForeignKey('shared_accounts.id'), nullable=True)
    added_by_user_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    shared_account     = db.relationship('SharedAccount', foreign_keys=[shared_account_id],
                                         backref=db.backref('expenses', lazy='dynamic'))
    added_by           = db.relationship('User', foreign_keys=[added_by_user_id])

    attachments  = db.relationship('ExpenseAttachment', backref='expense',
                                   lazy=True, cascade='all, delete-orphan')


class ExpenseAttachment(db.Model):
    __tablename__ = 'expense_attachments'

    id         = db.Column(db.Integer, primary_key=True)
    expense_id = db.Column(db.Integer,
                           db.ForeignKey('expenses.id', ondelete='CASCADE'),
                           nullable=False)
    filename   = db.Column(db.String(255), nullable=False)
    mime_type  = db.Column(db.String(100), nullable=False)
    data       = db.Column(db.LargeBinary, nullable=False)
    size       = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Debt(db.Model):
    __tablename__ = 'debts'

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    person_name = db.Column(db.String(100), nullable=False)
    amount      = db.Column(db.Numeric(12, 2), nullable=False)
    direction   = db.Column(db.String(4), nullable=False)   # 'owe' | 'owed'
    is_paid     = db.Column(db.Boolean, nullable=False, default=False)
    created_at  = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('debts', lazy='dynamic'))


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


class SharedAccountInvitation(db.Model):
    __tablename__ = 'shared_account_invitations'

    id                 = db.Column(db.Integer, primary_key=True)
    shared_account_id  = db.Column(db.Integer,
                                   db.ForeignKey('shared_accounts.id', ondelete='CASCADE'),
                                   nullable=False)
    invited_user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    invited_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status             = db.Column(db.String(10), nullable=False, default='pending')  # pending|accepted|declined
    created_at         = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    shared_account = db.relationship('SharedAccount',
                                     backref=db.backref('invitations', lazy='dynamic',
                                                        cascade='all, delete-orphan'))
    invited_user   = db.relationship('User', foreign_keys=[invited_user_id],
                                     backref=db.backref('received_invitations', lazy='dynamic'))
    invited_by     = db.relationship('User', foreign_keys=[invited_by_user_id])


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

def get_monthly_income(user_id=None, year=None, month=None, shared_account_id=None) -> float:
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


def get_monthly_summary(user_id=None, year=None, month=None, shared_account_id=None):
    if shared_account_id:
        expense_filter = (
            (Expense.shared_account_id == shared_account_id)
            & (Expense.is_spent.is_(True))
            & (extract('year',  Expense.expense_date) == year)
            & (extract('month', Expense.expense_date) == month)
        )
        member_ids = [m.user_id for m in SharedAccountMember.query.filter_by(
            shared_account_id=shared_account_id
        ).all()]
        cat_filter = db.or_(Category.user_id.is_(None), Category.user_id.in_(member_ids))
    else:
        expense_filter = (
            (Expense.user_id == user_id)
            & (Expense.shared_account_id.is_(None))
            & (Expense.is_spent.is_(True))
            & (extract('year',  Expense.expense_date) == year)
            & (extract('month', Expense.expense_date) == month)
        )
        cat_filter = db.or_(Category.user_id.is_(None), Category.user_id == user_id)

    rows = (
        db.session.query(
            Category.id,
            Category.name,
            Category.color,
            Category.icon,
            func.coalesce(func.sum(Expense.amount), 0).label('total'),
        )
        .outerjoin(Expense, (Expense.category_id == Category.id) & expense_filter)
        .filter(Category.is_active.is_(True), cat_filter)
        .group_by(Category.id, Category.name, Category.color, Category.icon)
        .order_by(func.coalesce(func.sum(Expense.amount), 0).desc())
        .all()
    )
    return rows


def get_budget_map(user_id=None, year=None, month=None, shared_account_id=None) -> dict:
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


def get_account_balance(account_id: int) -> float:
    """Balance = sum of remaining deposit Expense records for the account."""
    total = db.session.query(
        func.coalesce(func.sum(Expense.amount), 0)
    ).filter(Expense.savings_account_id == account_id).scalar()
    return float(total)


def get_savings_category() -> 'Category':
    """Return (creating if absent) the global system category «Накопления»."""
    cat = Category.query.filter_by(name='Накопления', user_id=None).first()
    if not cat:
        cat = Category(name='Накопления', icon='bi-piggy-bank', color='#0d6efd', user_id=None)
        db.session.add(cat)
        db.session.flush()
    return cat


_MONTH_NAMES_RU = [
    'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
    'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
]

def months_list():
    return [(m, _MONTH_NAMES_RU[m - 1]) for m in range(1, 13)]


def adjust_day(day: int, year: int, month: int) -> int:
    return min(day, calendar.monthrange(year, month)[1])


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
        .filter(Income.user_id == current_user.id,
                Income.savings_account_id.is_(None)).scalar()
    expense_count = Expense.query.filter_by(user_id=current_user.id).count()
    income_count  = Income.query.filter_by(user_id=current_user.id).count()

    # Годы с данными для выпадающего списка в экспорте
    exp_years = [r[0] for r in db.session.query(extract('year', Expense.expense_date).label('y'))
                 .filter(Expense.user_id == current_user.id).distinct().all()]
    inc_years = [r[0] for r in db.session.query(extract('year', Income.income_date).label('y'))
                 .filter(Income.user_id == current_user.id).distinct().all()]
    export_years = sorted(set(exp_years) | set(inc_years) | {today.year}, reverse=True)

    return render_template('profile.html',
                           total_expenses=float(total_expenses),
                           total_income=float(total_income),
                           expense_count=expense_count,
                           income_count=income_count,
                           today=today,
                           current_year=today.year,
                           export_years=export_years)


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


@app.route('/profile/export')
@login_required
@ban_check
def profile_export():
    today = date.today()
    try:
        year = int(request.args.get('year', today.year))
    except (ValueError, TypeError):
        year = today.year
    try:
        month = int(request.args.get('month', 0))
        if month not in range(0, 13):
            month = 0
    except (ValueError, TypeError):
        month = 0

    exp_q = Expense.query.filter(
        Expense.user_id == current_user.id,
        extract('year', Expense.expense_date) == year,
        Expense.savings_account_id.is_(None),
    )
    inc_q = Income.query.filter(
        Income.user_id == current_user.id,
        extract('year', Income.income_date) == year,
        Income.savings_account_id.is_(None),
    )
    if month:
        exp_q = exp_q.filter(extract('month', Expense.expense_date) == month)
        inc_q = inc_q.filter(extract('month', Income.income_date) == month)

    expenses = exp_q.join(Category).order_by(Expense.expense_date).all()
    incomes  = inc_q.order_by(Income.income_date).all()

    wb = openpyxl.Workbook()

    # ── Лист «Расходы» ────────────────────────────────────────────
    ws_exp = wb.active
    ws_exp.title = 'Расходы'
    exp_headers = ['Дата', 'Категория', 'Сумма', 'Описание', 'Плановый', 'Оплачен', 'Заметки']
    ws_exp.append(exp_headers)
    for cell in ws_exp[1]:
        cell.font = Font(bold=True)

    for exp in expenses:
        ws_exp.append([
            exp.expense_date.strftime('%d.%m.%Y'),
            exp.category.name,
            float(exp.amount),
            exp.description or '',
            'Да' if exp.is_planned else 'Нет',
            'Да' if exp.is_spent  else 'Нет',
            exp.notes or '',
        ])

    for col in ws_exp.columns:
        width = max(len(str(cell.value or '')) for cell in col) + 4
        ws_exp.column_dimensions[col[0].column_letter].width = min(width, 40)

    # ── Лист «Доходы» ────────────────────────────────────────────
    ws_inc = wb.create_sheet('Доходы')
    inc_headers = ['Дата', 'Источник', 'Сумма', 'Описание', 'Заметки']
    ws_inc.append(inc_headers)
    for cell in ws_inc[1]:
        cell.font = Font(bold=True)

    for inc in incomes:
        ws_inc.append([
            inc.income_date.strftime('%d.%m.%Y'),
            inc.source,
            float(inc.amount),
            inc.description or '',
            inc.notes or '',
        ])

    for col in ws_inc.columns:
        width = max(len(str(cell.value or '')) for cell in col) + 4
        ws_inc.column_dimensions[col[0].column_letter].width = min(width, 40)

    # ── Лист «Бюджет» ────────────────────────────────────────────
    bud_q = (MonthlyBudget.query
             .filter(MonthlyBudget.user_id == current_user.id,
                     MonthlyBudget.year == year)
             .join(Category)
             .order_by(MonthlyBudget.month, Category.name))
    if month:
        bud_q = bud_q.filter(MonthlyBudget.month == month)
    budgets = bud_q.all()

    ws_bud = wb.create_sheet('Бюджет')
    bud_headers = ['Год', 'Месяц', 'Категория', 'Сумма']
    ws_bud.append(bud_headers)
    for cell in ws_bud[1]:
        cell.font = Font(bold=True)

    for b in budgets:
        ws_bud.append([b.year, b.month, b.category.name, float(b.amount)])

    for col in ws_bud.columns:
        width = max(len(str(cell.value or '')) for cell in col) + 4
        ws_bud.column_dimensions[col[0].column_letter].width = min(width, 40)

    # ── Лист «Накопления» (счета) ─────────────────────────────────
    sav_accounts = SavingsAccount.query.filter_by(
        user_id=current_user.id, is_active=True
    ).order_by(SavingsAccount.name).all()

    ws_sav = wb.create_sheet('Накопления')
    ws_sav.append(['Название', 'Цвет', 'Иконка', 'Целевая сумма', 'Баланс'])
    for cell in ws_sav[1]:
        cell.font = Font(bold=True)
    for acc in sav_accounts:
        ws_sav.append([
            acc.name,
            acc.color,
            acc.icon,
            float(acc.target_amount) if acc.target_amount else '',
            get_account_balance(acc.id),
        ])
    for col in ws_sav.columns:
        width = max(len(str(cell.value or '')) for cell in col) + 4
        ws_sav.column_dimensions[col[0].column_letter].width = min(width, 40)

    # ── Лист «Нак. Операции» (пополнения) ────────────────────────
    sav_deps = (Expense.query
                .filter(Expense.user_id == current_user.id,
                        Expense.savings_account_id.isnot(None))
                .options(joinedload(Expense.savings_account))
                .order_by(Expense.expense_date).all())

    ws_sav_ops = wb.create_sheet('Нак. Операции')
    ws_sav_ops.append(['Дата', 'Счёт', 'Сумма', 'Описание'])
    for cell in ws_sav_ops[1]:
        cell.font = Font(bold=True)
    for dep in sav_deps:
        ws_sav_ops.append([
            dep.expense_date.strftime('%d.%m.%Y'),
            dep.savings_account.name if dep.savings_account else '',
            float(dep.amount),
            dep.description or '',
        ])
    for col in ws_sav_ops.columns:
        width = max(len(str(cell.value or '')) for cell in col) + 4
        ws_sav_ops.column_dimensions[col[0].column_letter].width = min(width, 40)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    month_names = ['','янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек']
    filename = f'расходы_доходы_{year}_{month_names[month]}.xlsx' if month else f'расходы_доходы_{year}.xlsx'
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@app.route('/profile/export/pdf')
@login_required
@ban_check
def profile_export_pdf():
    if weasyprint is None:
        flash('PDF экспорт недоступен: отсутствуют системные зависимости.', 'danger')
        return redirect(url_for('profile'))

    today = date.today()
    try:
        year  = int(request.args.get('year',  today.year))
        month = int(request.args.get('month', 0))
    except (ValueError, TypeError):
        year, month = today.year, 0

    if not month or month not in range(1, 13):
        flash('Для экспорта PDF выберите конкретный месяц.', 'warning')
        return redirect(url_for('profile'))

    pdf_bytes = _render_pdf(current_user.id, year, month)
    filename  = f'report_{year}_{month:02d}.pdf'
    return Response(
        pdf_bytes,
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@app.route('/profile/import', methods=['POST'])
@login_required
@ban_check
def profile_import():
    f = request.files.get('file')
    if not f or not f.filename:
        flash('Файл не выбран.', 'danger')
        return redirect(url_for('profile'))

    if not f.filename.lower().endswith('.xlsx'):
        flash('Допускается только формат .xlsx.', 'danger')
        return redirect(url_for('profile'))

    data = f.read()
    if len(data) > 5 * 1024 * 1024:
        flash('Файл слишком большой (максимум 5 МБ).', 'danger')
        return redirect(url_for('profile'))

    try:
        wb = openpyxl.load_workbook(filename=io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        flash('Не удалось прочитать файл. Убедитесь, что это корректный .xlsx.', 'danger')
        return redirect(url_for('profile'))

    exp_count = inc_count = skipped = sav_count = sav_ops_count = 0

    # ── Импорт расходов ───────────────────────────────────────────
    if 'Расходы' in wb.sheetnames:
        ws = wb['Расходы']
        rows = iter(ws.rows)
        next(rows, None)  # пропустить заголовок
        for row in rows:
            vals = [cell.value for cell in row]
            if len(vals) < 3:
                skipped += 1
                continue
            date_str, cat_name, amount_val = vals[0], vals[1], vals[2]
            desc    = str(vals[3]).strip() if len(vals) > 3 and vals[3] else ''
            planned = str(vals[4]).strip().lower() == 'да' if len(vals) > 4 and vals[4] else False
            spent   = str(vals[5]).strip().lower() == 'да' if len(vals) > 5 and vals[5] else True
            notes   = str(vals[6]).strip() if len(vals) > 6 and vals[6] else ''

            try:
                if isinstance(date_str, date):
                    exp_date = date_str
                else:
                    exp_date = datetime.strptime(str(date_str).strip(), '%d.%m.%Y').date()
            except (ValueError, TypeError):
                skipped += 1
                continue

            try:
                amount = float(amount_val)
                if amount <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                skipped += 1
                continue

            cat_name_str = str(cat_name).strip() if cat_name else 'Прочее'
            if not cat_name_str:
                cat_name_str = 'Прочее'

            category = Category.query.filter(
                db.func.lower(Category.name) == cat_name_str.lower(),
                db.or_(Category.user_id.is_(None), Category.user_id == current_user.id),
                Category.is_active.is_(True),
            ).first()

            if not category:
                category = Category(name=cat_name_str, user_id=current_user.id)
                db.session.add(category)
                db.session.flush()

            db.session.add(Expense(
                user_id      = current_user.id,
                category_id  = category.id,
                amount       = amount,
                description  = desc or None,
                expense_date = exp_date,
                is_planned   = planned,
                is_spent     = spent,
                notes        = notes or None,
            ))
            exp_count += 1

    # ── Импорт доходов ────────────────────────────────────────────
    if 'Доходы' in wb.sheetnames:
        ws = wb['Доходы']
        rows = iter(ws.rows)
        next(rows, None)  # пропустить заголовок
        for row in rows:
            vals = [cell.value for cell in row]
            if len(vals) < 3:
                skipped += 1
                continue
            date_str, source_val, amount_val = vals[0], vals[1], vals[2]
            desc  = str(vals[3]).strip() if len(vals) > 3 and vals[3] else ''
            notes = str(vals[4]).strip() if len(vals) > 4 and vals[4] else ''

            try:
                if isinstance(date_str, date):
                    inc_date = date_str
                else:
                    inc_date = datetime.strptime(str(date_str).strip(), '%d.%m.%Y').date()
            except (ValueError, TypeError):
                skipped += 1
                continue

            try:
                amount = float(amount_val)
                if amount <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                skipped += 1
                continue

            source = str(source_val).strip() if source_val else ''
            if not source:
                skipped += 1
                continue

            db.session.add(Income(
                user_id     = current_user.id,
                amount      = amount,
                source      = source,
                description = desc or None,
                income_date = inc_date,
                notes       = notes or None,
            ))
            inc_count += 1

    # ── Импорт бюджета ────────────────────────────────────────────
    bud_count = 0
    if 'Бюджет' in wb.sheetnames:
        ws = wb['Бюджет']
        rows = iter(ws.rows)
        next(rows, None)  # пропустить заголовок
        for row in rows:
            vals = [cell.value for cell in row]
            if len(vals) < 4:
                skipped += 1
                continue
            year_val, month_val, cat_name, amount_val = vals[0], vals[1], vals[2], vals[3]

            try:
                bud_year  = int(year_val)
                bud_month = int(month_val)
                if not (1 <= bud_month <= 12) or bud_year < 2000:
                    raise ValueError
            except (ValueError, TypeError):
                skipped += 1
                continue

            try:
                amount = float(amount_val)
                if amount <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                skipped += 1
                continue

            cat_name_str = str(cat_name).strip() if cat_name else 'Прочее'
            if not cat_name_str:
                cat_name_str = 'Прочее'

            category = Category.query.filter(
                db.func.lower(Category.name) == cat_name_str.lower(),
                db.or_(Category.user_id.is_(None), Category.user_id == current_user.id),
                Category.is_active.is_(True),
            ).first()

            if not category:
                category = Category(name=cat_name_str, user_id=current_user.id)
                db.session.add(category)
                db.session.flush()

            # Upsert: обновить если уже есть, иначе создать
            existing = MonthlyBudget.query.filter_by(
                user_id=current_user.id,
                category_id=category.id,
                year=bud_year,
                month=bud_month,
            ).first()

            if existing:
                existing.amount = amount
            else:
                db.session.add(MonthlyBudget(
                    user_id=current_user.id,
                    category_id=category.id,
                    year=bud_year,
                    month=bud_month,
                    amount=amount,
                ))
            bud_count += 1

    # ── Импорт накопительных счетов ──────────────────────────────
    if 'Накопления' in wb.sheetnames:
        ws = wb['Накопления']
        rows = iter(ws.rows)
        next(rows, None)
        for row in rows:
            vals = [cell.value for cell in row]
            if not vals or not vals[0]:
                skipped += 1
                continue
            name = str(vals[0]).strip()
            if not name:
                skipped += 1
                continue
            color = str(vals[1]).strip() if len(vals) > 1 and vals[1] else '#0d6efd'
            if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
                color = '#0d6efd'
            icon = str(vals[2]).strip() if len(vals) > 2 and vals[2] else 'bi-piggy-bank'
            target = None
            if len(vals) > 3 and vals[3]:
                try:
                    target = float(vals[3])
                    if target <= 0:
                        target = None
                except (ValueError, TypeError):
                    target = None

            existing = SavingsAccount.query.filter_by(
                user_id=current_user.id, name=name
            ).first()
            if existing:
                existing.color         = color
                existing.icon          = icon
                existing.target_amount = target
            else:
                db.session.add(SavingsAccount(
                    user_id=current_user.id, name=name,
                    color=color, icon=icon, target_amount=target,
                ))
            sav_count += 1

    # ── Импорт операций накоплений ────────────────────────────────
    if 'Нак. Операции' in wb.sheetnames:
        db.session.flush()
        ws = wb['Нак. Операции']
        rows = iter(ws.rows)
        next(rows, None)
        for row in rows:
            vals = [cell.value for cell in row]
            if len(vals) < 3:
                skipped += 1
                continue
            date_str, acc_name_val, amount_val = vals[0], vals[1], vals[2]
            desc = str(vals[3]).strip() if len(vals) > 3 and vals[3] else ''

            try:
                dep_date = date_str if isinstance(date_str, date) else \
                    datetime.strptime(str(date_str).strip(), '%d.%m.%Y').date()
            except (ValueError, TypeError):
                skipped += 1
                continue

            try:
                amount = float(amount_val)
                if amount <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                skipped += 1
                continue

            acc_name_str = str(acc_name_val).strip() if acc_name_val else ''
            if not acc_name_str:
                skipped += 1
                continue

            acc = SavingsAccount.query.filter_by(
                user_id=current_user.id, name=acc_name_str
            ).first()
            if not acc:
                skipped += 1
                continue

            cat = get_savings_category()
            db.session.add(Expense(
                user_id=current_user.id,
                category_id=cat.id,
                savings_account_id=acc.id,
                amount=amount,
                description=desc or f'Пополнение: {acc.name}',
                expense_date=dep_date,
                is_planned=False,
                is_spent=True,
            ))
            sav_ops_count += 1

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Ошибка при сохранении данных.', 'danger')
        return redirect(url_for('profile'))

    word_exp = 'расход' if exp_count == 1 else ('расхода' if exp_count < 5 else 'расходов')
    word_inc = 'доход'  if inc_count == 1 else ('дохода'  if inc_count < 5 else 'доходов')
    word_bud = 'запись бюджета' if bud_count == 1 else ('записи бюджета' if bud_count < 5 else 'записей бюджета')
    parts = [f'{exp_count} {word_exp}', f'{inc_count} {word_inc}', f'{bud_count} {word_bud}']
    if sav_count:
        word_sav = 'счёт' if sav_count == 1 else ('счёта' if sav_count < 5 else 'счетов')
        parts.append(f'{sav_count} {word_sav} накоплений')
    if sav_ops_count:
        word_ops = 'операция' if sav_ops_count == 1 else ('операции' if sav_ops_count < 5 else 'операций')
        parts.append(f'{sav_ops_count} {word_ops} накоплений')
    msg = 'Импортировано: ' + ', '.join(parts) + '.'
    if skipped:
        msg += f' Пропущено строк: {skipped}.'
    flash(msg, 'success')
    return redirect(url_for('profile'))


@app.route('/profile/clear-data', methods=['POST'])
@login_required
@ban_check
def profile_clear_data():
    try:
        Expense.query.filter_by(user_id=current_user.id).delete()
        Income.query.filter_by(user_id=current_user.id).delete()
        MonthlyBudget.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        flash('Все данные очищены.', 'warning')
    except Exception:
        db.session.rollback()
        flash('Ошибка при удалении данных.', 'danger')
    return redirect(url_for('profile'))


@app.route('/profile/budget-alert-pct', methods=['POST'])
@login_required
@ban_check
def profile_budget_alert_pct():
    alert_pct = request.form.get('budget_alert_pct', type=int)
    if alert_pct is None or not (1 <= alert_pct <= 100):
        flash('Порог должен быть от 1 до 100.', 'danger')
    else:
        current_user.budget_alert_pct = alert_pct
        db.session.commit()
        flash('Настройки сохранены.', 'success')
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

        total_spent_tmp = sum(float(r.total) for r in summary)
        balance_tmp     = total_income - total_spent_tmp
        prev_month_tmp  = month - 1 if month > 1 else 12
        prev_year_tmp   = year if month > 1 else year - 1
        current_empty   = (total_spent_tmp == 0 and total_income == 0)
        prev_has_expenses = Expense.query.filter_by(
            user_id=uid, is_planned=True
        ).filter(
            extract('year',  Expense.expense_date) == prev_year_tmp,
            extract('month', Expense.expense_date) == prev_month_tmp,
        ).count() > 0
        prev_has_income = Income.query.filter(
            Income.user_id == uid,
            Income.shared_account_id.is_(None),
            extract('year',  Income.income_date) == prev_year_tmp,
            extract('month', Income.income_date) == prev_month_tmp,
        ).count() > 0
        can_copy = current_empty and (prev_has_expenses or prev_has_income)

    total_spent = sum(float(r.total) for r in summary)
    balance     = total_income - total_spent

    daily_info = get_daily_budget_info(
        balance=balance,
        salary_day=current_user.salary_day,
        advance_day=current_user.advance_day,
    )

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


@app.route('/copy-from-previous', methods=['POST'])
@login_required
@ban_check
def copy_from_previous():
    year  = int(request.form['year'])
    month = int(request.form['month'])
    uid   = current_user.id

    prev_month = month - 1 if month > 1 else 12
    prev_year  = year if month > 1 else year - 1

    src_expenses = Expense.query.filter_by(
        user_id=uid, is_planned=True
    ).filter(
        extract('year',  Expense.expense_date) == prev_year,
        extract('month', Expense.expense_date) == prev_month,
    ).all()

    src_incomes = Income.query.filter(
        Income.user_id == uid,
        extract('year',  Income.income_date) == prev_year,
        extract('month', Income.income_date) == prev_month,
    ).all()

    month_names = {m: name for m, name in months_list()}

    for exp in src_expenses:
        new_day = adjust_day(exp.expense_date.day, year, month)
        db.session.add(Expense(
            user_id      = uid,
            category_id  = exp.category_id,
            amount       = exp.amount,
            description  = exp.description,
            notes        = exp.notes,
            expense_date = date(year, month, new_day),
            is_planned   = True,
            is_spent     = False,
        ))

    for inc in src_incomes:
        new_day = adjust_day(inc.income_date.day, year, month)
        db.session.add(Income(
            user_id     = uid,
            source      = inc.source,
            amount      = inc.amount,
            description = inc.description,
            notes       = inc.notes,
            income_date = date(year, month, new_day),
        ))

    db.session.commit()
    flash(
        f'Скопировано {len(src_expenses)} расходов и {len(src_incomes)} доходов '
        f'из {month_names[prev_month]}.',
        'success'
    )
    return redirect(url_for('index', year=year, month=month))


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
        spent_filter=spent_filter)


@app.route('/expenses/add', methods=['GET', 'POST'])
@login_required
@ban_check
def expense_add():
    categories = Category.query.filter(
        Category.is_active.is_(True),
        db.or_(Category.user_id.is_(None), Category.user_id == current_user.id)
    ).order_by(Category.name).all()
    if request.method == 'POST':
        ctx_type, ctx_id = get_active_context()
        try:
            exp = Expense(
                user_id           = current_user.id,
                category_id       = int(request.form['category_id']),
                amount            = float(request.form['amount']),
                description       = request.form.get('description', '').strip() or None,
                expense_date      = datetime.strptime(request.form['expense_date'], '%Y-%m-%d').date(),
                is_planned        = request.form.get('is_planned') == 'on',
                is_spent          = request.form.get('is_spent') == 'on',
                notes             = request.form.get('notes', '').strip() or None,
                shared_account_id = ctx_id if ctx_type == 'shared' else None,
                added_by_user_id  = current_user.id if ctx_type == 'shared' else None,
            )
            db.session.add(exp)
            db.session.flush()
            files = request.files.getlist('attachments')
            for f in files:
                if not f or not f.filename:
                    continue
                mime = f.mimetype or ''
                if mime not in ALLOWED_MIME_TYPES:
                    continue
                data = f.read()
                if len(data) > MAX_ATTACHMENT_SIZE:
                    continue
                db.session.add(ExpenseAttachment(
                    expense_id=exp.id,
                    filename=f.filename,
                    mime_type=mime,
                    data=data,
                    size=len(data),
                ))
            db.session.commit()
            flash('Расход добавлен!', 'success')
            ret_year  = request.form.get('ret_year',  type=int) or date.today().year
            ret_month = request.form.get('ret_month', type=int) or date.today().month
            return redirect(url_for('expenses_list', year=ret_year, month=ret_month))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка: {e}', 'danger')
    ret_year  = request.args.get('ret_year',  type=int) or date.today().year
    ret_month = request.args.get('ret_month', type=int) or date.today().month
    default_day = min(date.today().day, calendar.monthrange(ret_year, ret_month)[1])
    default_date = date(ret_year, ret_month, default_day)
    return render_template('expenses/form.html', categories=categories,
                           expense=None, today=default_date,
                           ret_year=ret_year, ret_month=ret_month)


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


@app.route('/expenses/<int:exp_id>/edit', methods=['GET', 'POST'])
@login_required
@ban_check
def expense_edit(exp_id):
    exp = get_expense_or_403(exp_id)
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
            exp.is_spent     = request.form.get('is_spent') == 'on'
            exp.notes        = request.form.get('notes', '').strip() or None
            db.session.commit()
            flash('Расход обновлён!', 'success')
            ret_year  = request.form.get('ret_year',  type=int) or date.today().year
            ret_month = request.form.get('ret_month', type=int) or date.today().month
            return redirect(url_for('expenses_list', year=ret_year, month=ret_month))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка: {e}', 'danger')
    ret_year  = request.args.get('ret_year',  type=int) or date.today().year
    ret_month = request.args.get('ret_month', type=int) or date.today().month
    return render_template('expenses/form.html', categories=categories,
                           expense=exp, today=date.today(),
                           ret_year=ret_year, ret_month=ret_month)


@app.route('/expenses/<int:exp_id>/delete', methods=['POST'])
@login_required
def expense_delete(exp_id):
    exp = get_expense_or_403(exp_id)
    db.session.delete(exp)
    db.session.commit()
    flash('Расход удалён.', 'warning')
    ret_year  = request.form.get('ret_year',  type=int) or date.today().year
    ret_month = request.form.get('ret_month', type=int) or date.today().month
    return redirect(url_for('expenses_list', year=ret_year, month=ret_month))


@app.context_processor
def inject_nav_month():
    today = date.today()
    nav_year  = request.args.get('year',  type=int) or today.year
    nav_month = request.args.get('month', type=int) or today.month
    return {'nav_year': nav_year, 'nav_month': nav_month}


@app.context_processor
def inject_reminders():
    if not current_user.is_authenticated:
        return {'reminders': []}
    tomorrow = date.today() + timedelta(days=1)
    reminders = Expense.query.filter_by(
        user_id=current_user.id, is_spent=False
    ).filter(Expense.expense_date == tomorrow).all()
    return {'reminders': reminders}


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
                           'color': row.color, 'level': 'exceeded',
                           'pct': int(_pct)})
        elif _pct >= threshold:
            alerts.append({'name': row.name, 'icon': row.icon,
                           'color': row.color, 'level': 'warning',
                           'pct': int(_pct)})
    return {'budget_alerts': alerts}


@app.context_processor
def inject_debt_summary():
    if not current_user.is_authenticated:
        return {'debt_summary': {'total_owe': 0, 'total_owed': 0,
                                 'count_owe': 0, 'count_owed': 0}}
    active = Debt.query.filter_by(user_id=current_user.id, is_paid=False).all()
    return {'debt_summary': {
        'total_owe':  sum(float(d.amount) for d in active if d.direction == 'owe'),
        'total_owed': sum(float(d.amount) for d in active if d.direction == 'owed'),
        'count_owe':  sum(1 for d in active if d.direction == 'owe'),
        'count_owed': sum(1 for d in active if d.direction == 'owed'),
    }}


@app.context_processor
def inject_shared_context():
    if not current_user.is_authenticated:
        return {'user_shared_accounts': [], 'active_shared_account': None,
                'pending_invitations': [], 'pending_invitations_count': 0}
    memberships = SharedAccountMember.query.filter_by(user_id=current_user.id).all()
    accounts = [m.shared_account for m in memberships]
    active_id = session.get('active_shared_account_id')
    active = next((a for a in accounts if a.id == active_id), None)
    pending = SharedAccountInvitation.query.filter_by(
        invited_user_id=current_user.id, status='pending'
    ).all()
    return {
        'user_shared_accounts': accounts,
        'active_shared_account': active,
        'pending_invitations': pending,
        'pending_invitations_count': len(pending),
    }


# ─── Shared account routes ────────────────────────────────────────────────────

@app.route('/shared/switch/personal')
@login_required
def shared_switch_personal():
    session.pop('active_shared_account_id', None)
    flash('Переключено на личный счёт.', 'info')
    return redirect(request.referrer or url_for('index'))


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
    members = SharedAccountMember.query.filter_by(shared_account_id=shared_id).all()
    invitations = SharedAccountInvitation.query.filter_by(
        shared_account_id=shared_id, status='pending'
    ).all()
    return render_template('shared/manage.html', account=sa, members=members,
                           invitations=invitations)


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

    if target.id == current_user.id:
        flash('Нельзя пригласить себя.', 'warning')
        return redirect(url_for('shared_manage', shared_id=shared_id))

    if SharedAccountMember.query.filter_by(shared_account_id=shared_id, user_id=target.id).first():
        flash(f'{target.username} уже является участником.', 'warning')
        return redirect(url_for('shared_manage', shared_id=shared_id))

    if SharedAccountInvitation.query.filter_by(
        shared_account_id=shared_id, invited_user_id=target.id, status='pending'
    ).first():
        flash(f'Приглашение для {target.username} уже отправлено.', 'warning')
        return redirect(url_for('shared_manage', shared_id=shared_id))

    db.session.add(SharedAccountInvitation(
        shared_account_id=shared_id,
        invited_user_id=target.id,
        invited_by_user_id=current_user.id,
    ))
    db.session.commit()
    flash(f'Приглашение отправлено пользователю {target.username}.', 'success')
    return redirect(url_for('shared_manage', shared_id=shared_id))


@app.route('/invitations/<int:inv_id>/accept', methods=['POST'])
@login_required
def invitation_accept(inv_id):
    inv = SharedAccountInvitation.query.filter_by(
        id=inv_id, invited_user_id=current_user.id, status='pending'
    ).first_or_404()
    inv.status = 'accepted'
    db.session.add(SharedAccountMember(
        shared_account_id=inv.shared_account_id, user_id=current_user.id
    ))
    db.session.commit()
    flash(f'Вы вступили в счёт «{inv.shared_account.name}»!', 'success')
    return redirect(url_for('index'))


@app.route('/invitations/<int:inv_id>/decline', methods=['POST'])
@login_required
def invitation_decline(inv_id):
    inv = SharedAccountInvitation.query.filter_by(
        id=inv_id, invited_user_id=current_user.id, status='pending'
    ).first_or_404()
    inv.status = 'declined'
    db.session.commit()
    flash('Приглашение отклонено.', 'info')
    return redirect(request.referrer or url_for('index'))


@app.route('/shared/<int:shared_id>/leave', methods=['POST'])
@login_required
@ban_check
@shared_member_required
def shared_leave(shared_id):
    sa = db.session.get(SharedAccount, shared_id)
    if not sa:
        abort(404)

    member_count = SharedAccountMember.query.filter_by(shared_account_id=shared_id).count()
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


@app.route('/expenses/<int:exp_id>/toggle-spent', methods=['POST'])
@login_required
def expense_toggle_spent(exp_id):
    exp = get_expense_or_403(exp_id)
    exp.is_spent = not exp.is_spent
    db.session.commit()
    return jsonify({'is_spent': exp.is_spent})


@app.route('/expenses/<int:exp_id>/copy', methods=['POST'])
@login_required
@ban_check
def expense_copy(exp_id):
    exp = Expense.query.filter_by(id=exp_id, user_id=current_user.id).first_or_404()
    data = request.get_json()
    months = data.get('months') if data else None
    if not months or not isinstance(months, list):
        return jsonify({'error': 'Укажите месяцы'}), 400

    today = date.today()
    current_year = today.year
    created = 0

    for m in months:
        if not isinstance(m, int) or not (1 <= m <= 12):
            continue
        max_day = calendar.monthrange(current_year, m)[1]
        target_day = min(exp.expense_date.day, max_day)
        target_date = date(current_year, m, target_day)
        is_spent = False if target_date > today else exp.is_spent
        copy = Expense(
            user_id      = current_user.id,
            category_id  = exp.category_id,
            amount       = exp.amount,
            description  = exp.description,
            expense_date = target_date,
            is_planned   = exp.is_planned,
            is_spent     = is_spent,
            notes        = exp.notes,
        )
        db.session.add(copy)
        created += 1

    try:
        db.session.commit()
        return jsonify({'created': created})
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Ошибка сохранения'}), 500


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


@app.route('/categories/<int:cat_id>', methods=['DELETE'])
@login_required
def category_delete(cat_id):
    cat = Category.query.filter_by(id=cat_id, user_id=current_user.id).first_or_404()
    in_use = Expense.query.filter_by(category_id=cat_id).count()
    if in_use:
        return jsonify({'error': f'Категория используется в {in_use} расход(ах)'}), 409
    try:
        db.session.delete(cat)
        db.session.commit()
        return jsonify({'ok': True})
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Ошибка сервера'}), 500


@app.route('/categories/<int:cat_id>', methods=['PATCH'])
@login_required
@ban_check
def category_edit(cat_id):
    cat = Category.query.filter_by(id=cat_id, user_id=current_user.id).first_or_404()
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400

    name  = (data.get('name') or '').strip()
    color = (data.get('color') or '').strip()

    if not name:
        return jsonify({'error': 'Название обязательно'}), 400
    if len(name) > 100:
        return jsonify({'error': 'Название слишком длинное'}), 400
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        return jsonify({'error': 'Неверный формат цвета'}), 400

    conflict = Category.query.filter(
        db.func.lower(Category.name) == name.lower(),
        db.or_(Category.user_id.is_(None), Category.user_id == current_user.id),
        Category.id != cat_id,
    ).first()
    if conflict:
        return jsonify({'error': f'Категория «{conflict.name}» уже существует'}), 409

    cat.name  = name
    cat.color = color
    try:
        db.session.commit()
        return jsonify({'id': cat.id, 'name': cat.name, 'color': cat.color})
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Ошибка сервера'}), 500


# ─── Attachments ──────────────────────────────────────────────────────────────

ALLOWED_MIME_TYPES  = {'image/jpeg', 'image/png', 'image/webp', 'application/pdf'}
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_ATTACHMENTS     = 10


@app.route('/attachments/<int:att_id>')
@login_required
def attachment_serve(att_id):
    att = ExpenseAttachment.query.get_or_404(att_id)
    if att.expense.user_id != current_user.id:
        return jsonify({'error': 'Доступ запрещён'}), 403
    return send_file(
        io.BytesIO(att.data),
        mimetype=att.mime_type,
        download_name=att.filename,
        as_attachment=False,
        max_age=3600,
    )


@app.route('/expenses/<int:exp_id>/attachments', methods=['POST'])
@login_required
@ban_check
def attachment_upload(exp_id):
    exp = Expense.query.filter_by(id=exp_id, user_id=current_user.id).first()
    if exp is None:
        return jsonify({'error': 'Расход не найден'}), 403

    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'Файл не передан'}), 400

    mime = f.mimetype or ''
    if mime not in ALLOWED_MIME_TYPES:
        return jsonify({'error': 'Недопустимый тип файла'}), 415

    data = f.read()
    if len(data) > MAX_ATTACHMENT_SIZE:
        return jsonify({'error': 'Файл слишком большой (макс. 10 МБ)'}), 413

    if ExpenseAttachment.query.filter_by(expense_id=exp_id).count() >= MAX_ATTACHMENTS:
        return jsonify({'error': 'Максимум 10 вложений на расход'}), 409

    att = ExpenseAttachment(
        expense_id=exp_id,
        filename=f.filename or 'file',
        mime_type=mime,
        data=data,
        size=len(data),
    )
    try:
        db.session.add(att)
        db.session.commit()
        return jsonify({'id': att.id, 'filename': att.filename,
                        'mime_type': att.mime_type, 'size': att.size}), 201
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Ошибка сохранения'}), 500


@app.route('/attachments/<int:att_id>', methods=['DELETE'])
@login_required
def attachment_delete(att_id):
    att = ExpenseAttachment.query.get_or_404(att_id)
    if att.expense.user_id != current_user.id:
        return jsonify({'error': 'Доступ запрещён'}), 403
    try:
        db.session.delete(att)
        db.session.commit()
        return jsonify({'ok': True})
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Ошибка удаления'}), 500


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

    ctx_type, ctx_id = get_active_context()
    budget_map = get_budget_map(user_id=(None if ctx_type == 'shared' else uid),
                                year=year, month=month,
                                shared_account_id=(ctx_id if ctx_type == 'shared' else None))

    if request.method == 'POST':
        year  = int(request.form['year'])
        month = int(request.form['month'])
        ctx_type, ctx_id = get_active_context()
        for cat in categories:
            val = request.form.get(f'budget_{cat.id}', '').strip()
            if ctx_type == 'shared':
                existing = MonthlyBudget.query.filter_by(
                    shared_account_id=ctx_id, category_id=cat.id, year=year, month=month
                ).first()
            else:
                existing = MonthlyBudget.query.filter(
                    MonthlyBudget.user_id == uid,
                    MonthlyBudget.shared_account_id.is_(None),
                    MonthlyBudget.category_id == cat.id,
                    MonthlyBudget.year == year,
                    MonthlyBudget.month == month,
                ).first()
            if val:
                amount = float(val)
                if existing:
                    existing.amount = amount
                else:
                    db.session.add(MonthlyBudget(
                        user_id=uid, category_id=cat.id,
                        year=year, month=month, amount=amount,
                        shared_account_id=ctx_id if ctx_type == 'shared' else None,
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

    ctx_type, ctx_id = get_active_context()
    if ctx_type == 'shared':
        incomes = Income.query.filter(
            Income.shared_account_id == ctx_id,
            extract('year',  Income.income_date) == year,
            extract('month', Income.income_date) == month,
            Income.savings_account_id.is_(None),
        ).order_by(Income.income_date.desc(), Income.created_at.desc()).all()
    else:
        incomes = Income.query.filter(
            Income.user_id == ctx_id,
            Income.shared_account_id.is_(None),
            extract('year',  Income.income_date) == year,
            extract('month', Income.income_date) == month,
            Income.savings_account_id.is_(None),
        ).order_by(Income.income_date.desc(), Income.created_at.desc()).all()

    total = sum(float(i.amount) for i in incomes)
    return render_template('income/list.html',
                           incomes=incomes, total=total,
                           year=year, month=month, months=months_list())


@app.route('/income/add', methods=['GET', 'POST'])
@login_required
@ban_check
def income_add():
    if request.method == 'POST':
        ctx_type, ctx_id = get_active_context()
        try:
            inc = Income(
                user_id           = current_user.id,
                amount            = float(request.form['amount']),
                source            = request.form['source'].strip(),
                description       = request.form.get('description', '').strip() or None,
                income_date       = datetime.strptime(request.form['income_date'], '%Y-%m-%d').date(),
                notes             = request.form.get('notes', '').strip() or None,
                shared_account_id = ctx_id if ctx_type == 'shared' else None,
                added_by_user_id  = current_user.id if ctx_type == 'shared' else None,
            )
            db.session.add(inc)
            db.session.commit()
            flash('Доход добавлен!', 'success')
            ret_year  = request.form.get('ret_year',  type=int) or date.today().year
            ret_month = request.form.get('ret_month', type=int) or date.today().month
            return redirect(url_for('income_list', year=ret_year, month=ret_month))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка: {e}', 'danger')
    ret_year  = request.args.get('ret_year',  type=int) or date.today().year
    ret_month = request.args.get('ret_month', type=int) or date.today().month
    default_day = min(date.today().day, calendar.monthrange(ret_year, ret_month)[1])
    default_date = date(ret_year, ret_month, default_day)
    return render_template('income/form.html', income=None, today=default_date,
                           ret_year=ret_year, ret_month=ret_month)


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


@app.route('/income/<int:inc_id>/edit', methods=['GET', 'POST'])
@login_required
@ban_check
def income_edit(inc_id):
    inc = get_income_or_403(inc_id)
    if request.method == 'POST':
        try:
            inc.amount      = float(request.form['amount'])
            inc.source      = request.form['source'].strip()
            inc.description = request.form.get('description', '').strip() or None
            inc.income_date = datetime.strptime(request.form['income_date'], '%Y-%m-%d').date()
            inc.notes       = request.form.get('notes', '').strip() or None
            db.session.commit()
            flash('Доход обновлён!', 'success')
            ret_year  = request.form.get('ret_year',  type=int) or date.today().year
            ret_month = request.form.get('ret_month', type=int) or date.today().month
            return redirect(url_for('income_list', year=ret_year, month=ret_month))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка: {e}', 'danger')
    ret_year  = request.args.get('ret_year',  type=int) or date.today().year
    ret_month = request.args.get('ret_month', type=int) or date.today().month
    return render_template('income/form.html', income=inc, today=date.today(),
                           ret_year=ret_year, ret_month=ret_month)


@app.route('/income/<int:inc_id>/delete', methods=['POST'])
@login_required
def income_delete(inc_id):
    inc = get_income_or_403(inc_id)
    db.session.delete(inc)
    db.session.commit()
    flash('Доход удалён.', 'warning')
    ret_year  = request.form.get('ret_year',  type=int) or date.today().year
    ret_month = request.form.get('ret_month', type=int) or date.today().month
    return redirect(url_for('income_list', year=ret_year, month=ret_month))


# ─── Накопительные счета ──────────────────────────────────────────────────────

SAVINGS_ICONS = [
    ('bi-piggy-bank',       'Копилка'),
    ('bi-airplane',         'Путешествие'),
    ('bi-car-front',        'Авто'),
    ('bi-house',            'Жильё'),
    ('bi-laptop',           'Техника'),
    ('bi-phone',            'Телефон'),
    ('bi-heart-pulse',      'Здоровье'),
    ('bi-book',             'Образование'),
    ('bi-shield',           'Подушка'),
    ('bi-gift',             'Подарок'),
    ('bi-music-note-beamed','Хобби'),
    ('bi-bicycle',          'Спорт'),
    ('bi-bag',              'Шопинг'),
    ('bi-bank2',            'Вклад'),
    ('bi-cash-coin',        'Деньги'),
    ('bi-heart',            'Любовь'),
    ('bi-stars',            'Мечта'),
    ('bi-tools',            'Ремонт'),
    ('bi-camera',           'Фото'),
    ('bi-fire',             'Срочное'),
]

MAX_SAVINGS_IMAGE = 2 * 1024 * 1024  # 2 MB


def _parse_savings_form(form, files, acc=None):
    """Parse create/edit form, return dict of fields or None on error (sets flash)."""
    name = form.get('name', '').strip()
    if not name:
        flash('Название обязательно.', 'danger')
        return None
    if len(name) > 100:
        flash('Название слишком длинное.', 'danger')
        return None
    color = form.get('color', '#0d6efd').strip()
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        color = '#0d6efd'
    icon = form.get('icon', 'bi-piggy-bank').strip() or 'bi-piggy-bank'
    raw_target = form.get('target_amount', '').strip()
    target = None
    if raw_target:
        try:
            target = float(raw_target)
            if target <= 0:
                raise ValueError
        except (ValueError, TypeError):
            flash('Неверная целевая сумма.', 'danger')
            return None
    image_data = image_mime = None
    if form.get('clear_image') == '1':
        image_data, image_mime = None, None
    else:
        f = files.get('image')
        if f and f.filename:
            mime = f.mimetype or ''
            if not mime.startswith('image/'):
                flash('Допускаются только изображения.', 'danger')
                return None
            data = f.read()
            if len(data) > MAX_SAVINGS_IMAGE:
                flash('Изображение слишком большое (макс. 2 МБ).', 'danger')
                return None
            image_data, image_mime = data, mime
        elif acc:
            image_data = acc.image_data
            image_mime = acc.image_mime
    return {'name': name, 'color': color, 'icon': icon, 'target': target,
            'image_data': image_data, 'image_mime': image_mime}


@app.route('/savings')
@login_required
@ban_check
def savings_list():
    uid = current_user.id
    accounts = SavingsAccount.query.filter_by(
        user_id=uid, is_active=True
    ).order_by(SavingsAccount.created_at.asc()).all()

    account_data = []
    for acc in accounts:
        balance  = get_account_balance(acc.id)
        tx_count = (Expense.query.filter_by(savings_account_id=acc.id).count() +
                    Income.query.filter_by(savings_account_id=acc.id).count())
        pct = None
        if acc.target_amount and float(acc.target_amount) > 0:
            pct = min(round(balance / float(acc.target_amount) * 100, 1), 100.0)
        recent_ops = []
        for d in (Expense.query.filter_by(savings_account_id=acc.id)
                  .order_by(Expense.expense_date.desc(), Expense.created_at.desc())
                  .limit(5).all()):
            recent_ops.append({
                'type': 'deposit',
                'amount': float(d.amount),
                'description': d.description or 'Пополнение',
                'date': d.expense_date.strftime('%d.%m.%Y'),
            })
        for w in (Income.query.filter_by(savings_account_id=acc.id)
                  .order_by(Income.income_date.desc(), Income.created_at.desc())
                  .limit(5).all()):
            recent_ops.append({
                'type': 'withdrawal',
                'amount': float(w.amount),
                'description': w.description or 'Снятие',
                'date': w.income_date.strftime('%d.%m.%Y'),
            })
        recent_ops.sort(key=lambda x: x['date'], reverse=True)
        account_data.append({
            'acc': acc, 'balance': balance, 'tx_count': tx_count,
            'pct': pct, 'recent_ops': recent_ops[:5],
        })

    deposits = (Expense.query
                .filter(Expense.user_id == uid, Expense.savings_account_id.isnot(None))
                .options(joinedload(Expense.savings_account)).all())
    withdrawals = (Income.query
                   .filter(Income.user_id == uid, Income.savings_account_id.isnot(None))
                   .options(joinedload(Income.savings_account)).all())

    history = []
    for d in deposits:
        history.append({
            'type': 'deposit', 'amount': float(d.amount),
            'description': d.description, 'date': d.expense_date,
            'account_name':  d.savings_account.name  if d.savings_account else '—',
            'account_color': d.savings_account.color if d.savings_account else '#6c757d',
        })
    for w in withdrawals:
        history.append({
            'type': 'withdrawal', 'amount': float(w.amount),
            'description': w.description, 'date': w.income_date,
            'account_name':  w.savings_account.name  if w.savings_account else '—',
            'account_color': w.savings_account.color if w.savings_account else '#6c757d',
        })
    history.sort(key=lambda x: x['date'], reverse=True)

    open_acc_id = request.args.get('acc', type=int)

    return render_template('savings/list.html',
                           account_data=account_data,
                           history=history[:50],
                           today=date.today(),
                           open_acc_id=open_acc_id)


@app.route('/savings/add', methods=['POST'])
@login_required
@ban_check
def savings_add():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Название обязательно'}), 400
    if len(name) > 100:
        return jsonify({'error': 'Название слишком длинное'}), 400
    color = (data.get('color') or '#0d6efd').strip()
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        return jsonify({'error': 'Неверный формат цвета'}), 400
    icon = (data.get('icon') or 'bi-piggy-bank').strip()
    target = None
    raw_target = data.get('target_amount')
    if raw_target not in (None, ''):
        try:
            target = float(raw_target)
            if target <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return jsonify({'error': 'Неверная целевая сумма'}), 400
    acc = SavingsAccount(user_id=current_user.id, name=name, color=color,
                         icon=icon, target_amount=target)
    try:
        db.session.add(acc)
        db.session.commit()
        return jsonify({'id': acc.id, 'name': acc.name}), 201
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Ошибка сервера'}), 500


@app.route('/savings/new', methods=['GET', 'POST'])
@login_required
@ban_check
def savings_new():
    if request.method == 'POST':
        fields = _parse_savings_form(request.form, request.files)
        if fields is None:
            return render_template('savings/form.html', acc=None,
                                   savings_icons=SAVINGS_ICONS)
        acc = SavingsAccount(
            user_id=current_user.id,
            name=fields['name'], color=fields['color'], icon=fields['icon'],
            target_amount=fields['target'],
            image_data=fields['image_data'], image_mime=fields['image_mime'],
        )
        db.session.add(acc)
        db.session.commit()
        flash('Счёт создан!', 'success')
        return redirect(url_for('savings_list'))
    return render_template('savings/form.html', acc=None, savings_icons=SAVINGS_ICONS)


@app.route('/savings/<int:acc_id>/edit', methods=['GET', 'POST'])
@login_required
@ban_check
def savings_edit(acc_id):
    acc = SavingsAccount.query.filter_by(id=acc_id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        fields = _parse_savings_form(request.form, request.files, acc=acc)
        if fields is None:
            return render_template('savings/form.html', acc=acc,
                                   savings_icons=SAVINGS_ICONS)
        acc.name          = fields['name']
        acc.color         = fields['color']
        acc.icon          = fields['icon']
        acc.target_amount = fields['target']
        acc.image_data    = fields['image_data']
        acc.image_mime    = fields['image_mime']
        db.session.commit()
        flash('Счёт обновлён!', 'success')
        return redirect(url_for('savings_list'))
    return render_template('savings/form.html', acc=acc, savings_icons=SAVINGS_ICONS)


@app.route('/savings/<int:acc_id>/image')
@login_required
def savings_image(acc_id):
    acc = SavingsAccount.query.filter_by(id=acc_id, user_id=current_user.id).first_or_404()
    if not acc.image_data:
        abort(404)
    return send_file(
        io.BytesIO(acc.image_data),
        mimetype=acc.image_mime,
        max_age=3600,
    )


@app.route('/savings/<int:acc_id>', methods=['DELETE'])
@login_required
def savings_delete(acc_id):
    acc = SavingsAccount.query.filter_by(id=acc_id, user_id=current_user.id).first_or_404()
    try:
        Expense.query.filter_by(savings_account_id=acc_id).delete()
        Income.query.filter_by(savings_account_id=acc_id).delete()
        db.session.delete(acc)
        db.session.commit()
        return jsonify({'ok': True})
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Ошибка сервера'}), 500


@app.route('/savings/<int:acc_id>/deposit', methods=['POST'])
@login_required
@ban_check
def savings_deposit(acc_id):
    acc = SavingsAccount.query.filter_by(id=acc_id, user_id=current_user.id).first_or_404()
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400
    try:
        amount = float(data['amount'])
        if amount <= 0:
            raise ValueError
    except (ValueError, KeyError, TypeError):
        return jsonify({'error': 'Неверная сумма'}), 400
    try:
        txn_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
    except (ValueError, KeyError, TypeError):
        return jsonify({'error': 'Неверная дата'}), 400
    description = (data.get('description') or '').strip() or f'Пополнение: {acc.name}'
    cat = get_savings_category()
    exp = Expense(
        user_id=current_user.id,
        category_id=cat.id,
        savings_account_id=acc_id,
        amount=amount,
        description=description,
        expense_date=txn_date,
        is_planned=False,
        is_spent=True,
    )
    db.session.add(exp)
    try:
        db.session.commit()
        return jsonify({'ok': True, 'balance': get_account_balance(acc_id)})
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Ошибка сохранения'}), 500


@app.route('/savings/<int:acc_id>/withdraw', methods=['POST'])
@login_required
@ban_check
def savings_withdraw(acc_id):
    acc = SavingsAccount.query.filter_by(id=acc_id, user_id=current_user.id).first_or_404()
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400
    try:
        amount = float(data['amount'])
        if amount <= 0:
            raise ValueError
    except (ValueError, KeyError, TypeError):
        return jsonify({'error': 'Неверная сумма'}), 400
    try:
        datetime.strptime(data['date'], '%Y-%m-%d').date()
    except (ValueError, KeyError, TypeError):
        return jsonify({'error': 'Неверная дата'}), 400
    balance = get_account_balance(acc_id)
    if amount > balance:
        return jsonify({'error': f'Недостаточно средств. Баланс: {balance:.2f} ₽'}), 400
    # Reduce deposit expenses FIFO (oldest first)
    deposits = Expense.query.filter_by(
        savings_account_id=acc_id
    ).order_by(Expense.expense_date.asc(), Expense.created_at.asc()).all()
    remaining = amount
    for dep in deposits:
        if remaining <= 0:
            break
        dep_amount = float(dep.amount)
        if dep_amount <= remaining:
            remaining -= dep_amount
            db.session.delete(dep)
        else:
            dep.amount = round(dep_amount - remaining, 2)
            remaining = 0
    try:
        db.session.commit()
        return jsonify({'ok': True, 'balance': get_account_balance(acc_id)})
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Ошибка сохранения'}), 500


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
    ALLOWED = {'❤️', '👍', '😢', '👎'}
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


# ─── API ──────────────────────────────────────────────────────────────────────

@app.route('/api/chart-data')
@login_required
def chart_data():
    today = date.today()
    year  = int(request.args.get('year',  today.year))
    month = int(request.args.get('month', today.month))
    ctx_type, ctx_id = get_active_context()
    if ctx_type == 'shared':
        rows = get_monthly_summary(year=year, month=month, shared_account_id=ctx_id)
    else:
        rows = get_monthly_summary(user_id=ctx_id, year=year, month=month)
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
    ctx, ctx_id = get_active_context()
    is_shared = ctx == 'shared'

    # ── Блок сравнения ────────────────────────────────────────────────
    py, pm = _prev_period(year, month, mode)

    def cat_totals(y, m):
        if is_shared:
            expense_filter = (
                (Expense.category_id == Category.id)
                & (Expense.shared_account_id == ctx_id)
                & (extract('year',  Expense.expense_date) == y)
                & (extract('month', Expense.expense_date) == m)
            )
            cat_filter = Category.is_active.is_(True)
        else:
            expense_filter = (
                (Expense.category_id == Category.id)
                & (Expense.user_id == uid)
                & (Expense.shared_account_id.is_(None))
                & (extract('year',  Expense.expense_date) == y)
                & (extract('month', Expense.expense_date) == m)
            )
            cat_filter = db.and_(
                Category.is_active.is_(True),
                db.or_(Category.user_id.is_(None), Category.user_id == uid)
            )
        rows = (
            db.session.query(
                Category.id,
                Category.name,
                Category.color,
                Category.icon,
                func.coalesce(func.sum(Expense.amount), 0).label('total'),
            )
            .outerjoin(Expense, expense_filter)
            .filter(cat_filter)
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
        if is_shared:
            inc = float(db.session.query(
                func.coalesce(func.sum(Income.amount), 0)
            ).filter(
                Income.shared_account_id == ctx_id,
                extract('year',  Income.income_date) == cy,
                extract('month', Income.income_date) == cm,
                Income.savings_account_id.is_(None),
            ).scalar())
            exp = float(db.session.query(
                func.coalesce(func.sum(Expense.amount), 0)
            ).filter(
                Expense.shared_account_id == ctx_id,
                extract('year',  Expense.expense_date) == cy,
                extract('month', Expense.expense_date) == cm,
            ).scalar())
        else:
            inc = float(db.session.query(
                func.coalesce(func.sum(Income.amount), 0)
            ).filter(
                Income.user_id == uid,
                Income.shared_account_id.is_(None),
                extract('year',  Income.income_date) == cy,
                extract('month', Income.income_date) == cm,
                Income.savings_account_id.is_(None),
            ).scalar())
            exp = float(db.session.query(
                func.coalesce(func.sum(Expense.amount), 0)
            ).filter(
                Expense.user_id == uid,
                Expense.shared_account_id.is_(None),
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


# ─── ИИ-помощник (Groq) ───────────────────────────────────────────────────────
_groq_client = Groq(api_key=os.getenv('GROQ_API_KEY'), timeout=60.0) if os.getenv('GROQ_API_KEY') else None

_SAVINGS_ICON_MAP = {label.lower(): cls for cls, label in SAVINGS_ICONS}

_RU_MONTH_MAP = {
    'январ': 1, 'феврал': 2, 'март': 3, 'апрел': 4,
    'ма': 5, 'июн': 6, 'июл': 7, 'август': 8,
    'сентябр': 9, 'октябр': 10, 'ноябр': 11, 'декабр': 12,
}

_RU_MONTH_NAMES = {
    1: 'январь', 2: 'февраль', 3: 'март', 4: 'апрель',
    5: 'май', 6: 'июнь', 7: 'июль', 8: 'август',
    9: 'сентябрь', 10: 'октябрь', 11: 'ноябрь', 12: 'декабрь',
}


def _svg_donut(segments: list) -> str:
    """Return an SVG donut chart string for the given segments."""
    R, r, cx, cy = 90, 55, 100, 100
    total = sum(s['value'] for s in segments if s['value'] > 0)

    if not segments or total == 0:
        return (
            '<svg viewBox="0 0 200 200" width="180" height="180" '
            'xmlns="http://www.w3.org/2000/svg">'
            f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="#e9ecef"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="white"/>'
            '</svg>'
        )

    paths = []
    start = -math.pi / 2  # top

    for seg in segments:
        if seg['value'] <= 0:
            continue
        sweep = (seg['value'] / total) * 2 * math.pi
        end   = start + sweep
        large = 1 if sweep > math.pi else 0

        x1 = cx + R * math.cos(start);  y1 = cy + R * math.sin(start)
        x2 = cx + R * math.cos(end);    y2 = cy + R * math.sin(end)
        x3 = cx + r * math.cos(end);    y3 = cy + r * math.sin(end)
        x4 = cx + r * math.cos(start);  y4 = cy + r * math.sin(start)

        d = (f"M {x1:.3f} {y1:.3f} A {R} {R} 0 {large} 1 {x2:.3f} {y2:.3f} "
             f"L {x3:.3f} {y3:.3f} A {r} {r} 0 {large} 0 {x4:.3f} {y4:.3f} Z")
        paths.append(f'<path d="{d}" fill="{seg["color"]}"/>')
        start = end

    return (
        '<svg viewBox="0 0 200 200" width="180" height="180" '
        'xmlns="http://www.w3.org/2000/svg">'
        + ''.join(paths) +
        '</svg>'
    )


def _build_pdf_context(user_id: int, year: int, month: int) -> dict:
    summary   = get_monthly_summary(user_id, year, month)
    income    = get_monthly_income(user_id, year, month)
    total_exp = 0.0
    cats: list = []

    for row in summary:
        t = float(row.total)
        if t > 0:
            total_exp += t
            cats.append({'name': row.name, 'color': row.color, 'total': t, 'pct': 0.0})

    if total_exp > 0:
        for cat in cats:
            cat['pct'] = round(cat['total'] / total_exp * 100, 1)

    cats.sort(key=lambda x: x['total'], reverse=True)
    segments = [{'color': c['color'], 'value': c['total'], 'label': c['name']} for c in cats]

    return {
        'username':   current_user.username,
        'year':       year,
        'month':      month,
        'month_name': _RU_MONTH_NAMES[month],
        'generated':  date.today().strftime('%d.%m.%Y'),
        'income':     income,
        'expenses':   total_exp,
        'balance':    income - total_exp,
        'categories': cats,
        'svg_chart':  _svg_donut(segments),
    }


def _render_pdf(user_id: int, year: int, month: int) -> bytes:
    ctx  = _build_pdf_context(user_id, year, month)
    html = render_template('pdf/monthly_report.html', **ctx)
    return weasyprint.HTML(string=html, base_url=request.host_url).write_pdf()


def _qdata_category_month(user_id: int, cat, month: int, year: int) -> str:
    month_start = date(year, month, 1)
    month_end   = date(year, month, calendar.monthrange(year, month)[1])
    total = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.user_id == user_id,
        Expense.category_id == cat.id,
        Expense.is_spent.is_(True),
        Expense.expense_date.between(month_start, month_end),
    ).scalar())
    count = Expense.query.filter(
        Expense.user_id == user_id,
        Expense.category_id == cat.id,
        Expense.is_spent.is_(True),
        Expense.expense_date.between(month_start, month_end),
    ).count()
    return (
        f"\nQUERY DATA (расходы по категории):\n"
        f"{cat.name}, {_RU_MONTH_NAMES[month]} {year}: {total:.0f} ₽ ({count} оп.)"
    )


def _qdata_monthly_summary(user_id: int, month: int, year: int) -> str:
    summary   = get_monthly_summary(user_id, year, month)
    income    = get_monthly_income(user_id, year, month)
    total_exp = sum(float(r.total) for r in summary)
    lines = [
        f"\nQUERY DATA (сводка за месяц):",
        f"{_RU_MONTH_NAMES[month].capitalize()} {year} | "
        f"доходы: {income:.0f} ₽ | расходы: {total_exp:.0f} ₽ | остаток: {income - total_exp:.0f} ₽",
    ]
    for r in summary:
        if float(r.total) > 0:
            lines.append(f"  {r.name:<20} {float(r.total):>8.0f} ₽")
    return '\n'.join(lines)


def _qdata_recent(user_id: int, n: int) -> str:
    exps = (Expense.query
        .filter_by(user_id=user_id)
        .order_by(Expense.expense_date.desc(), Expense.id.desc())
        .limit(n).all())
    lines = [f"\nQUERY DATA (последние {n} расходов):"]
    for e in exps:
        desc = e.description or '—'
        lines.append(
            f"ID:{e.id} {float(e.amount):.0f}₽ {e.category.name} {desc} {e.expense_date:%d.%m.%Y}"
        )
    return '\n'.join(lines)


def _qdata_comparison(user_id: int, m1: tuple, m2: tuple) -> str:
    def _totals(month, year):
        s   = get_monthly_summary(user_id, year, month)
        inc = get_monthly_income(user_id, year, month)
        exp = sum(float(r.total) for r in s)
        return inc, exp

    inc1, exp1 = _totals(m1[0], m1[1])
    inc2, exp2 = _totals(m2[0], m2[1])

    if exp1 > 0:
        pct   = (exp2 - exp1) / exp1 * 100
        delta = f"+{pct:.1f}%" if pct >= 0 else f"{pct:.1f}%"
    else:
        delta = "н/д"

    return '\n'.join([
        f"\nQUERY DATA (сравнение месяцев):",
        f"{_RU_MONTH_NAMES[m1[0]].capitalize()} {m1[1]}: расходы {exp1:.0f} ₽, доходы {inc1:.0f} ₽",
        f"{_RU_MONTH_NAMES[m2[0]].capitalize()} {m2[1]}: расходы {exp2:.0f} ₽, доходы {inc2:.0f} ₽",
        f"Изменение расходов: {delta}",
    ])


def _qdata_savings(user_id: int) -> str:
    accounts = SavingsAccount.query.filter_by(user_id=user_id, is_active=True).all()
    if not accounts:
        return "\nQUERY DATA (накопления):\nНакопительных счетов нет."
    lines = ["\nQUERY DATA (накопления):"]
    for acc in accounts:
        bal = get_account_balance(acc.id)
        if acc.target_amount and float(acc.target_amount) > 0:
            pct = round(bal / float(acc.target_amount) * 100, 1)
            lines.append(
                f"{acc.name}: {bal:.0f} ₽ (цель {float(acc.target_amount):.0f} ₽, {pct}%)"
            )
        else:
            lines.append(f"{acc.name}: {bal:.0f} ₽")
    return '\n'.join(lines)


def _extract_query_data(message: str, user_id: int, categories: list) -> str:
    """Detect query intent, run DB query, return QUERY DATA block for the system prompt."""
    today = date.today()
    msg   = message.lower().strip()

    # 1. Detect months (up to 2)
    detected_months: list = []
    for prefix, month_num in _RU_MONTH_MAP.items():
        if prefix in msg:
            year  = today.year if month_num <= today.month else today.year - 1
            entry = (month_num, year)
            if entry not in detected_months:
                detected_months.append(entry)

    # 2. Detect category
    detected_cat = _find_category_by_name(msg, categories)

    # 3. Keyword flags
    is_savings_q  = any(k in msg for k in ('накоплени', 'сбережени', 'счёт', 'счет', 'баланс'))
    is_recent_q   = any(k in msg for k in ('последни', 'покажи', 'что купил', 'что потратил', 'что брал', 'история'))
    is_query_word = any(k in msg for k in ('сколько', 'итого', 'всего', 'топ', 'больше всего',
                                            'на что', 'сводк', 'потратил', 'расход', 'ушло', 'трат'))
    is_compare    = (len(detected_months) >= 2 or
                     ('сравни' in msg and len(detected_months) >= 1))

    # 4. Branch
    if is_savings_q:
        return _qdata_savings(user_id)

    if is_compare:
        months = detected_months[:2]
        if len(months) == 1:
            months.append((today.month, today.year))
        return _qdata_comparison(user_id, months[0], months[1])

    if is_recent_q:
        nums = re.findall(r'\d+', msg)
        n = min(int(nums[0]), 20) if nums else 10
        return _qdata_recent(user_id, n)

    if detected_cat and detected_months and is_query_word:
        m, y = detected_months[0]
        return _qdata_category_month(user_id, detected_cat, m, y)

    if detected_months and is_query_word:
        m, y = detected_months[0]
        return _qdata_monthly_summary(user_id, m, y)

    return ''


def _parse_date(val) -> 'date | None':
    if not val:
        return None
    if isinstance(val, date):
        return val
    s = str(val).strip()
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass
    s_lower = s.lower()
    for prefix, month_num in _RU_MONTH_MAP.items():
        if prefix in s_lower:
            return date(date.today().year, month_num, 1)
    return None

_SAVINGS_COLOR_MAP = {
    'синий': '#0d6efd', 'blue': '#0d6efd',
    'зелёный': '#198754', 'зеленый': '#198754', 'green': '#198754',
    'красный': '#dc3545', 'red': '#dc3545',
    'жёлтый': '#ffc107', 'желтый': '#ffc107', 'yellow': '#ffc107',
    'оранжевый': '#fd7e14', 'orange': '#fd7e14',
    'фиолетовый': '#6f42c1', 'purple': '#6f42c1',
    'розовый': '#e83e8c', 'pink': '#e83e8c',
    'голубой': '#0dcaf0', 'cyan': '#0dcaf0',
    'серый': '#6c757d', 'gray': '#6c757d',
    'чёрный': '#212529', 'черный': '#212529', 'black': '#212529',
}


def _build_chat_context(user_id: int, shared_account_id: int = None) -> dict:
    today = date.today()
    categories = Category.query.filter(
        Category.is_active.is_(True),
        db.or_(Category.user_id.is_(None), Category.user_id == user_id)
    ).order_by(Category.name).all()

    if shared_account_id:
        monthly_income = float(db.session.query(
            func.coalesce(func.sum(Income.amount), 0)
        ).filter(
            Income.shared_account_id == shared_account_id,
            extract('year',  Income.income_date) == today.year,
            extract('month', Income.income_date) == today.month,
            Income.savings_account_id.is_(None),
        ).scalar())
        monthly_expenses = float(db.session.query(
            func.coalesce(func.sum(Expense.amount), 0)
        ).filter(
            Expense.shared_account_id == shared_account_id,
            extract('year',  Expense.expense_date) == today.year,
            extract('month', Expense.expense_date) == today.month,
            Expense.is_spent.is_(True),
            Expense.savings_account_id.is_(None),
        ).scalar())
        recent_expenses = (Expense.query
            .filter_by(shared_account_id=shared_account_id)
            .order_by(Expense.expense_date.desc(), Expense.id.desc())
            .limit(5).all())
        recent_income = (Income.query
            .filter_by(shared_account_id=shared_account_id)
            .order_by(Income.income_date.desc(), Income.id.desc())
            .limit(3).all())
        shared_account = SharedAccount.query.get(shared_account_id)
        shared_account_name = shared_account.name if shared_account else '—'
    else:
        monthly_income = get_monthly_income(user_id, today.year, today.month)
        monthly_expenses = float(db.session.query(
            func.coalesce(func.sum(Expense.amount), 0)
        ).filter(
            Expense.user_id == user_id,
            Expense.shared_account_id.is_(None),
            extract('year',  Expense.expense_date) == today.year,
            extract('month', Expense.expense_date) == today.month,
            Expense.is_spent.is_(True),
            Expense.savings_account_id.is_(None),
        ).scalar())
        recent_expenses = (Expense.query
            .filter_by(user_id=user_id)
            .filter(Expense.shared_account_id.is_(None))
            .order_by(Expense.expense_date.desc(), Expense.id.desc())
            .limit(5).all())
        recent_income = (Income.query
            .filter_by(user_id=user_id)
            .filter(Income.shared_account_id.is_(None))
            .order_by(Income.income_date.desc(), Income.id.desc())
            .limit(3).all())
        shared_account_name = None

    active_debts = Debt.query.filter_by(user_id=user_id, is_paid=False).order_by(Debt.created_at.desc()).all()

    return {
        'today': today.isoformat(),
        'categories': categories,
        'monthly_income': monthly_income,
        'monthly_expenses': monthly_expenses,
        'remaining': monthly_income - monthly_expenses,
        'recent_expenses': recent_expenses,
        'recent_income': recent_income,
        'active_debts': active_debts,
        'shared_account_id': shared_account_id,
        'shared_account_name': shared_account_name,
    }


def _build_system_prompt(ctx: dict, query_data: str = '') -> str:
    cat_names = ', '.join(c.name for c in ctx['categories'])

    exp_lines = '\n'.join(
        f"ID:{e.id} {float(e.amount):.0f}₽ {e.category.name} {e.expense_date}"
        for e in ctx['recent_expenses']
    ) or '-'

    inc_lines = '\n'.join(
        f"ID:{i.id} {float(i.amount):.0f}₽ {i.source} {i.income_date}"
        for i in ctx['recent_income']
    ) or '-'

    debt_lines = '\n'.join(
        f"ID:{d.id} {float(d.amount):.0f}₽ {'я должен' if d.direction=='owe' else 'мне должны'} {d.person_name}"
        for d in ctx['active_debts']
    ) or '-'

    icons = 'Копилка,Путешествие,Авто,Жильё,Техника,Телефон,Здоровье,Образование,Подушка,Подарок,Хобби,Спорт,Шопинг,Вклад,Деньги,Любовь,Мечта,Ремонт,Фото,Срочное'
    colors = 'синий,зелёный,красный,жёлтый,оранжевый,фиолетовый,розовый,голубой,серый,чёрный'
    year = date.today().year

    shared_block = ''
    if ctx.get('shared_account_id'):
        shared_block = f"""
CURRENT MODE: SHARED ACCOUNT «{ctx['shared_account_name']}»
— You are in a SHARED account. All add_expense and add_income actions go to this shared account by default.
— If the user explicitly says "личный"/"в личный счёт"/"мой личный" — add param "personal":true to route to personal account instead.
— Shared account is for joint expenses/income (rent, groceries, utilities, trips together, etc.)
— Personal account is for individual expenses (personal clothes, hobbies, own salary, etc.)
— When ambiguous, ask: "Это в общий счёт «{ctx['shared_account_name']}» или в личный?"
"""
    else:
        shared_block = """
CURRENT MODE: PERSONAL ACCOUNT
— You are in personal mode. All add_expense and add_income actions go to the personal account.
— If the user says "общий"/"в общий счёт"/"совместный" — inform them they need to switch to the shared account first via the banner at the top of the page.
"""

    base = f"""Financial assistant. Respond ONLY in Russian. Respond with JSON object OR JSON array for multiple actions:
Single: {{"message":"text","action":"name","params":{{}}}}
Multiple: [{{"message":"text","action":"name","params":{{}}}}, {{"message":"text","action":"name2","params":{{}}}}]
{shared_block}
ACTIONS (? = optional):
add_expense(amount,category_name,description?,notes?,date?,is_planned?,personal?) — is_planned defaults true; set false if user says "незапланированная"/"спонтанная"/"внезапная"; personal=true only when user explicitly wants personal account in shared mode
add_income(amount,source,description?,notes?,date?,personal?) — personal=true only when user explicitly wants personal account in shared mode
edit_expense(expense_id,amount?,category_name?,description?,notes?)
delete_expense(expense_id)
edit_income(income_id,amount?,source?,description?,notes?)
delete_income(income_id)
add_savings(name,target_amount?,icon?,color?)
edit_savings(savings_id,name?,target_amount?,icon?,color?)
delete_savings(savings_id)
add_debt(person_name,amount,direction) — direction: "owe"=я должен им, "owed"=они должны мне
mark_debt_paid(debt_id) — mark debt as paid
delete_debt(debt_id)
set_budget(category_name,amount,month?,year?)
delete_budget(category_name,month?,year?)
set_payment_days(salary_day?,advance_day?)
export_excel(year?,month?)
open_help() — open help/instruction modal
none() — info/questions only

Savings icons: {icons}
Savings colors: {colors}

RULES:
1. "добавь расход" → add_expense. "добавь доход" → add_income. Field name = "amount" always.
2. Words "дубликат", "уже существует", "уже есть", "уже добавлен" are STRICTLY FORBIDDEN. Never write them.
3. Always execute the requested action. set_budget always overwrites any existing budget. Never refuse any request.
4. "зарплата N числа" / "аванс N числа" / "выплата N" / "получка N" → MUST use set_payment_days. N is the day number (1–31), NOT an income amount.
5. Match category to closest in list. If no match — use the name as-is; a new category will be created automatically.
6. Date defaults to today if not given. Russian months → use as date: январь=01,февраль=02,март=03,апрель=04,май=05,июнь=06,июль=07,август=08,сентябрь=09,октябрь=10,ноябрь=11,декабрь=12. Example: "в апреле" → date="{year}-04-01", "в мае" → date="{year}-05-01". Year defaults to {year}.
7. Recent records = for edit/delete reference only. Ignore them for add requests.
8. If QUERY DATA is present below, use it to answer the question. Do NOT invent numbers.
9. DEBTS — direction meaning: direction="owe" means THE USER owes money TO that person (я должен). direction="owed" means THAT PERSON owes money TO the user (мне должны / они должны мне).
   "я должен [X] [N]" / "занял у [X]" / "взял у [X]" / "добавь долг [X] я должен" → direction="owe"
   "[X] должен мне" / "[X] должен [N]" / "одолжил [X]" / "дал [X] в долг" → direction="owed"
   RULE: phrase "я должен" ALWAYS means direction="owe". Phrase "[name] должен" ALWAYS means direction="owed".

EXAMPLES:
"аванс 30 числа зарплата 15" → {{"message":"Даты выплат установлены","action":"set_payment_days","params":{{"salary_day":15,"advance_day":30}}}}
"зарплата 15 числа аванс 30 числа" → {{"message":"Даты выплат установлены","action":"set_payment_days","params":{{"salary_day":15,"advance_day":30}}}}
"укажи даты зарплата 10 аванс 25" → {{"message":"Даты выплат установлены","action":"set_payment_days","params":{{"salary_day":10,"advance_day":25}}}}
"добавь доход 300 пирожок" → {{"message":"Доход 300₽ добавлен","action":"add_income","params":{{"amount":300,"source":"пирожок"}}}}
"я должен Денису 500" → {{"message":"Долг добавлен","action":"add_debt","params":{{"person_name":"Денис","amount":500,"direction":"owe"}}}}
"занял у мамы 1000" → {{"message":"Долг добавлен","action":"add_debt","params":{{"person_name":"мама","amount":1000,"direction":"owe"}}}}
"Петя должен мне 2000" → {{"message":"Долг добавлен","action":"add_debt","params":{{"person_name":"Петя","amount":2000,"direction":"owed"}}}}
"одолжил Коле 500" → {{"message":"Долг добавлен","action":"add_debt","params":{{"person_name":"Коля","amount":500,"direction":"owed"}}}}

TODAY: {ctx['today']} | income {ctx['monthly_income']:.0f}₽ | expenses {ctx['monthly_expenses']:.0f}₽ | remaining {ctx['remaining']:.0f}₽
CATEGORIES: {cat_names}

Expenses:
{exp_lines}
Income:
{inc_lines}
Active debts:
{debt_lines}"""
    return base + query_data


def _find_category_by_name(name: str, categories: list) -> 'Category | None':
    name_l = name.lower().strip()
    for c in categories:
        if c.name.lower() == name_l:
            return c
    for c in categories:
        if name_l in c.name.lower() or c.name.lower() in name_l:
            return c
    return None


def _execute_chat_action(action: str, params: dict, user_id: int, ctx: dict) -> 'str | None':
    today = date.today()

    if action == 'add_expense':
        cat = _find_category_by_name(params.get('category_name', ''), ctx['categories'])
        if not cat:
            cat_name = (params.get('category_name') or '').strip()
            if not cat_name:
                cat_names = ', '.join(c.name for c in ctx['categories'])
                return f"Укажи категорию. Доступные: {cat_names}"
            # Создаём новую категорию автоматически
            import random as _rnd
            _palette = ['#4361ee','#e8115b','#198754','#0dcaf0','#fd7e14',
                        '#6f42c1','#20c997','#ffc107','#dc3545','#0d6efd']
            cat = Category(
                name=cat_name,
                color=_rnd.choice(_palette),
                icon='bi-tag',
                user_id=user_id,
            )
            db.session.add(cat)
            db.session.flush()
            ctx['categories'].append(cat)
        exp_date = _parse_date(params.get('date')) or today
        shared_id = ctx.get('shared_account_id')
        if params.get('personal'):
            shared_id = None
        exp = Expense(
            user_id=user_id,
            category_id=cat.id,
            amount=float(params['amount']),
            description=params.get('description') or None,
            notes=params.get('notes') or None,
            expense_date=exp_date,
            is_planned=bool(params.get('is_planned', True)),
            is_spent=True,
            shared_account_id=shared_id,
        )
        db.session.add(exp)
        db.session.commit()
        return None

    if action == 'add_income':
        inc_date = _parse_date(params.get('date')) or today
        shared_id = ctx.get('shared_account_id')
        if params.get('personal'):
            shared_id = None
        inc = Income(
            user_id=user_id,
            amount=float(params['amount']),
            source=params.get('source', 'Прочее').strip(),
            description=params.get('description') or None,
            notes=params.get('notes') or None,
            income_date=inc_date,
            shared_account_id=shared_id,
        )
        db.session.add(inc)
        db.session.commit()
        return None

    if action == 'edit_expense':
        exp = Expense.query.filter_by(id=params.get('expense_id'), user_id=user_id).first()
        if not exp:
            return 'Расход не найден.'
        if params.get('amount'):
            exp.amount = float(params['amount'])
        if params.get('category_name'):
            cat = _find_category_by_name(params['category_name'], ctx['categories'])
            if cat:
                exp.category_id = cat.id
        if params.get('description'):
            exp.description = params['description']
        if params.get('notes'):
            exp.notes = params['notes']
        db.session.commit()
        return None

    if action == 'delete_expense':
        exp = Expense.query.filter_by(id=params.get('expense_id'), user_id=user_id).first()
        if not exp:
            return 'Расход не найден.'
        db.session.delete(exp)
        db.session.commit()
        return None

    if action == 'edit_income':
        inc = Income.query.filter_by(id=params.get('income_id'), user_id=user_id).first()
        if not inc:
            return 'Доход не найден.'
        if params.get('amount'):
            inc.amount = float(params['amount'])
        if params.get('source'):
            inc.source = params['source'].strip()
        if params.get('description'):
            inc.description = params['description']
        if params.get('notes'):
            inc.notes = params['notes']
        db.session.commit()
        return None

    if action == 'delete_income':
        inc = Income.query.filter_by(id=params.get('income_id'), user_id=user_id).first()
        if not inc:
            return 'Доход не найден.'
        db.session.delete(inc)
        db.session.commit()
        return None

    if action in ('export_excel', 'open_help'):
        return None  # обрабатывается на фронтенде

    if action == 'set_payment_days':
        user = db.session.get(User, user_id)
        changed = False
        if params.get('salary_day') is not None:
            day = int(params['salary_day'])
            if 1 <= day <= 31:
                user.salary_day = day
                changed = True
        if params.get('advance_day') is not None:
            day = int(params['advance_day'])
            if 1 <= day <= 31:
                user.advance_day = day
                changed = True
        if changed:
            db.session.commit()
        return None

    if action == 'set_budget':
        cat = _find_category_by_name(params.get('category_name', ''), ctx['categories'])
        if not cat:
            return f"Категория «{params.get('category_name')}» не найдена. Доступные: {', '.join(c.name for c in ctx['categories'])}"
        try:
            amount = float(params['amount'])
        except (KeyError, TypeError, ValueError):
            return 'Укажи сумму лимита.'
        today = date.today()
        year  = int(params.get('year')  or today.year)
        month = int(params.get('month') or today.month)
        budget = MonthlyBudget.query.filter_by(
            user_id=user_id, category_id=cat.id, year=year, month=month
        ).first()
        if budget:
            budget.amount = amount
        else:
            db.session.add(MonthlyBudget(user_id=user_id, category_id=cat.id,
                                         year=year, month=month, amount=amount))
        db.session.commit()
        return None

    if action == 'delete_budget':
        cat = _find_category_by_name(params.get('category_name', ''), ctx['categories'])
        if not cat:
            return f"Категория «{params.get('category_name')}» не найдена."
        today = date.today()
        year  = int(params.get('year')  or today.year)
        month = int(params.get('month') or today.month)
        budget = MonthlyBudget.query.filter_by(
            user_id=user_id, category_id=cat.id, year=year, month=month
        ).first()
        if budget:
            db.session.delete(budget)
            db.session.commit()
        return None

    if action == 'add_savings':
        name = (params.get('name') or '').strip()
        if not name:
            return 'Укажи название накопительного счёта.'
        icon_raw = (params.get('icon') or 'копилка').lower().strip()
        icon_cls = _SAVINGS_ICON_MAP.get(icon_raw, 'bi-piggy-bank')
        color_raw = (params.get('color') or '').lower().strip()
        if re.fullmatch(r'#[0-9a-fA-F]{6}', color_raw):
            color = color_raw
        else:
            color = _SAVINGS_COLOR_MAP.get(color_raw, '#0d6efd')
        target = None
        if params.get('target_amount'):
            try:
                target = float(params['target_amount'])
            except (ValueError, TypeError):
                pass
        acc = SavingsAccount(user_id=user_id, name=name, icon=icon_cls,
                             color=color, target_amount=target)
        db.session.add(acc)
        db.session.commit()
        return None

    if action == 'edit_savings':
        acc = SavingsAccount.query.filter_by(id=params.get('savings_id'), user_id=user_id).first()
        if not acc:
            return 'Накопительный счёт не найден.'
        if params.get('name'):
            acc.name = params['name'].strip()
        if params.get('icon'):
            acc.icon = _SAVINGS_ICON_MAP.get(params['icon'].lower().strip(), acc.icon)
        if params.get('color'):
            c = params['color'].lower().strip()
            acc.color = c if re.fullmatch(r'#[0-9a-fA-F]{6}', c) else _SAVINGS_COLOR_MAP.get(c, acc.color)
        if params.get('target_amount') is not None:
            try:
                acc.target_amount = float(params['target_amount'])
            except (ValueError, TypeError):
                pass
        db.session.commit()
        return None

    if action == 'delete_savings':
        acc = SavingsAccount.query.filter_by(id=params.get('savings_id'), user_id=user_id).first()
        if not acc:
            return 'Накопительный счёт не найден.'
        acc.is_active = False
        db.session.commit()
        return None

    if action == 'add_debt':
        person    = (params.get('person_name') or '').strip()
        direction = params.get('direction', 'owe')
        if not person or direction not in ('owe', 'owed'):
            return 'Укажи имя и направление долга (owe/owed).'
        try:
            amount = float(params['amount'])
            if amount <= 0:
                raise ValueError
        except (ValueError, KeyError):
            return 'Некорректная сумма долга.'
        db.session.add(Debt(user_id=user_id, person_name=person, amount=amount, direction=direction))
        db.session.commit()
        return None

    if action == 'mark_debt_paid':
        debt = Debt.query.filter_by(id=params.get('debt_id'), user_id=user_id).first()
        if not debt:
            return 'Долг не найден.'
        debt.is_paid = True
        db.session.commit()
        return None

    if action == 'delete_debt':
        debt = Debt.query.filter_by(id=params.get('debt_id'), user_id=user_id).first()
        if not debt:
            return 'Долг не найден.'
        db.session.delete(debt)
        db.session.commit()
        return None

    return None


CHAT_WRITE_ACTIONS = {'add_expense', 'add_income', 'edit_expense', 'delete_expense',
                      'edit_income', 'delete_income', 'add_savings', 'edit_savings',
                      'delete_savings', 'set_budget', 'delete_budget', 'set_payment_days',
                      'add_debt', 'mark_debt_paid', 'delete_debt'}


@app.route('/api/chat', methods=['POST'])
@login_required
@ban_check
def api_chat():
    if not _groq_client:
        return jsonify({'message': 'ИИ-помощник не настроен (отсутствует GROQ_API_KEY).', 'ok': False}), 503

    try:
        data = request.get_json(silent=True) or {}
        user_message = (data.get('message') or '').strip()
        history_msgs = data.get('history') or []

        if not user_message:
            return jsonify({'message': 'Пустое сообщение.', 'ok': False}), 400

        _, ctx_shared_id = get_active_context()
        ctx           = _build_chat_context(current_user.id, ctx_shared_id if _ == 'shared' else None)
        query_data    = _extract_query_data(user_message, current_user.id, ctx['categories'])
        system_prompt = _build_system_prompt(ctx, query_data)

        messages = [{'role': 'system', 'content': system_prompt}]
        for h in history_msgs[-10:]:
            if h.get('role') in ('user', 'assistant') and h.get('content'):
                messages.append({'role': h['role'], 'content': str(h['content'])})
        messages.append({'role': 'user', 'content': user_message})
    except Exception as e:
        app.logger.error('Chat setup error: %s', e, exc_info=True)
        return jsonify({'message': f'Ошибка: {e}', 'ok': False}), 503

    uid = current_user.id

    @stream_with_context
    def generate():
        full = ''
        try:
            stream = _groq_client.chat.completions.create(
                model='llama-3.1-8b-instant',
                messages=messages,
                response_format={'type': 'json_object'},
                temperature=0.1,
                max_tokens=256,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content or ''
                if delta:
                    full += delta
                    yield f"data: {json.dumps({'d': delta})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'err': str(e)})}\n\n"
            return

        try:
            parsed = json.loads(full)
        except Exception:
            yield f"data: {json.dumps({'done': True, 'ok': False, 'msg': 'Ошибка ответа ИИ.'})}\n\n"
            return

        # LLM может вернуть список действий (когда просят несколько вещей сразу)
        items = parsed if isinstance(parsed, list) else [parsed]
        _SUCCESS_WORDS = ('добавлен', 'создан', 'выполнен', 'установлен', 'удалён', 'удален', 'обновлён', 'обновлен')
        _EXIST_WORDS   = ('уже существует', 'уже есть', 'уже добавлен', 'уже установлен', 'дубликат')

        msgs_out  = []
        any_write = False
        all_ok    = True
        export_url = None
        do_help   = False

        for item in items:
            if not isinstance(item, dict):
                continue
            action = item.get('action', 'none')
            params = item.get('params') or {}
            msg    = item.get('message', '')

            # ЛLM говорит "уже существует" — это галлюцинация, принудительно выполняем действие
            if any(w in msg.lower() for w in _EXIST_WORDS):
                action = 'none'  # сбрасываем чтобы не дублировать, но сообщение заменяем
                msgs_out.append('Не удалось выполнить: попробуй сформулировать запрос иначе.')
                all_ok = False
                continue
            # ЛLM говорит "добавлено" но action=none — галлюцинация
            if action == 'none' and any(w in msg.lower() for w in _SUCCESS_WORDS):
                app.logger.warning('LLM hallucination: action=none but message says success')
                msgs_out.append('Не удалось выполнить. Попробуй написать запросы по отдельности.')
                all_ok = False
                continue

            app.logger.info('Chat action=%s params=%s', action, params)

            try:
                err = _execute_chat_action(action, params, uid, ctx)
            except Exception as e:
                app.logger.error('Action execute error: %s', e, exc_info=True)
                db.session.rollback()
                msgs_out.append(f'Ошибка: {e}')
                all_ok = False
                continue

            if err:
                msgs_out.append(err)
                all_ok = False
            else:
                msgs_out.append(msg)
                if action in CHAT_WRITE_ACTIONS:
                    any_write = True
                if action == 'export_excel':
                    year  = int(params.get('year')  or date.today().year)
                    month = int(params.get('month') or 0)
                    export_url = f'/profile/export?year={year}&month={month}'
                if action == 'open_help':
                    do_help = True

        combined = ' | '.join(msgs_out) if msgs_out else ''
        yield f"data: {json.dumps({'done': True, 'ok': all_ok, 'msg': combined, 'reload': any_write, 'url': export_url, 'open_help': do_help})}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


with app.app_context():
    db.create_all()
    # Добавляем новые колонки если их ещё нет (safe migration)
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    columns = [c['name'] for c in inspector.get_columns('users')]
    if 'budget_alert_pct' not in columns:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN budget_alert_pct INTEGER NOT NULL DEFAULT 80;"))
            conn.commit()
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
    exp_columns = [c['name'] for c in inspector.get_columns('expenses')]
    if 'is_spent' not in exp_columns:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE expenses ADD COLUMN is_spent BOOLEAN NOT NULL DEFAULT TRUE;"))
            conn.commit()
    # ── savings_accounts migration ────────────────────────────────
    if 'savings_account_id' not in exp_columns:
        with db.engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE expenses ADD COLUMN savings_account_id INTEGER NULL "
                "REFERENCES savings_accounts(id);"
            ))
            conn.commit()
    inc_columns = [c['name'] for c in inspector.get_columns('incomes')]
    if 'savings_account_id' not in inc_columns:
        with db.engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE incomes ADD COLUMN savings_account_id INTEGER NULL "
                "REFERENCES savings_accounts(id);"
            ))
            conn.commit()
    # savings_accounts: image columns
    sav_columns = [c['name'] for c in inspector.get_columns('savings_accounts')]
    if 'image_data' not in sav_columns:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE savings_accounts ADD COLUMN image_data BYTEA;"))
            conn.commit()
    if 'image_mime' not in sav_columns:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE savings_accounts ADD COLUMN image_mime VARCHAR(50);"))
            conn.commit()
    # ── shared accounts migration ─────────────────────────────────
    exp_columns2 = [c['name'] for c in inspector.get_columns('expenses')]
    if 'shared_account_id' not in exp_columns2:
        with db.engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE expenses ADD COLUMN shared_account_id INTEGER NULL "
                "REFERENCES shared_accounts(id);"
            ))
            conn.commit()
    if 'added_by_user_id' not in exp_columns2:
        with db.engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE expenses ADD COLUMN added_by_user_id INTEGER NULL "
                "REFERENCES users(id);"
            ))
            conn.commit()
    inc_columns2 = [c['name'] for c in inspector.get_columns('incomes')]
    if 'shared_account_id' not in inc_columns2:
        with db.engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE incomes ADD COLUMN shared_account_id INTEGER NULL "
                "REFERENCES shared_accounts(id);"
            ))
            conn.commit()
    if 'added_by_user_id' not in inc_columns2:
        with db.engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE incomes ADD COLUMN added_by_user_id INTEGER NULL "
                "REFERENCES users(id);"
            ))
            conn.commit()
    bud_columns = [c['name'] for c in inspector.get_columns('monthly_budgets')]
    if 'shared_account_id' not in bud_columns:
        with db.engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE monthly_budgets ADD COLUMN shared_account_id INTEGER NULL "
                "REFERENCES shared_accounts(id);"
            ))
            conn.commit()
    sav_columns2 = [c['name'] for c in inspector.get_columns('savings_accounts')]
    if 'shared_account_id' not in sav_columns2:
        with db.engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE savings_accounts ADD COLUMN shared_account_id INTEGER NULL "
                "REFERENCES shared_accounts(id);"
            ))
            conn.commit()
    # Seed system «Накопления» category
    if not Category.query.filter_by(name='Накопления', user_id=None).first():
        db.session.add(Category(
            name='Накопления', icon='bi-piggy-bank', color='#0d6efd', user_id=None,
        ))
        db.session.commit()

# ─── Трекер долгов ────────────────────────────────────────────────────────────

@app.route('/debts')
@login_required
@ban_check
def debts_list():
    filter_val = request.args.get('filter', 'active')
    q = Debt.query.filter_by(user_id=current_user.id)
    if filter_val == 'owe':
        q = q.filter_by(direction='owe', is_paid=False)
    elif filter_val == 'owed':
        q = q.filter_by(direction='owed', is_paid=False)
    elif filter_val == 'paid':
        q = q.filter_by(is_paid=True)
    else:  # 'active'
        q = q.filter_by(is_paid=False)
    debts = q.order_by(Debt.created_at.desc()).all()

    all_active = Debt.query.filter_by(user_id=current_user.id, is_paid=False).all()
    total_owe  = sum(float(d.amount) for d in all_active if d.direction == 'owe')
    total_owed = sum(float(d.amount) for d in all_active if d.direction == 'owed')

    return render_template('debts/list.html',
        debts=debts, filter_val=filter_val,
        total_owe=total_owe, total_owed=total_owed)


@app.route('/debts/add', methods=['POST'])
@login_required
@ban_check
def debt_add():
    person    = request.form.get('person_name', '').strip()
    direction = request.form.get('direction', 'owe')
    if not person or direction not in ('owe', 'owed'):
        flash('Заполните все поля.', 'danger')
        return redirect(url_for('debts_list'))
    try:
        amount = float(request.form['amount'])
        if amount <= 0:
            raise ValueError
    except (ValueError, KeyError):
        flash('Некорректная сумма.', 'danger')
        return redirect(url_for('debts_list'))
    db.session.add(Debt(
        user_id=current_user.id, person_name=person,
        amount=amount, direction=direction,
    ))
    db.session.commit()
    flash('Долг добавлен.', 'success')
    return redirect(url_for('debts_list'))


@app.route('/debts/<int:debt_id>/toggle-paid', methods=['POST'])
@login_required
@ban_check
def debt_toggle_paid(debt_id):
    debt = Debt.query.filter_by(id=debt_id, user_id=current_user.id).first_or_404()
    debt.is_paid = not debt.is_paid
    db.session.commit()
    return redirect(url_for('debts_list'))


@app.route('/debts/<int:debt_id>/delete', methods=['POST'])
@login_required
@ban_check
def debt_delete(debt_id):
    debt = Debt.query.filter_by(id=debt_id, user_id=current_user.id).first_or_404()
    db.session.delete(debt)
    db.session.commit()
    flash('Долг удалён.', 'success')
    return redirect(url_for('debts_list'))


@app.route('/debts/<int:debt_id>/edit', methods=['GET', 'POST'])
@login_required
@ban_check
def debt_edit(debt_id):
    debt = Debt.query.filter_by(id=debt_id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        person    = request.form.get('person_name', '').strip()
        direction = request.form.get('direction', debt.direction)
        if not person or direction not in ('owe', 'owed'):
            flash('Заполните все поля.', 'danger')
            return redirect(url_for('debt_edit', debt_id=debt_id))
        try:
            amount = float(request.form['amount'])
            if amount <= 0:
                raise ValueError
        except (ValueError, KeyError):
            flash('Некорректная сумма.', 'danger')
            return redirect(url_for('debt_edit', debt_id=debt_id))
        debt.person_name = person
        debt.amount      = amount
        debt.direction   = direction
        db.session.commit()
        flash('Долг обновлён.', 'success')
        return redirect(url_for('debts_list'))
    return render_template('debts/edit.html', debt=debt)


@app.route('/offline')
def offline_page():
    return render_template('offline.html')


if __name__ == '__main__':
    host  = os.getenv('FLASK_HOST', '127.0.0.1')
    port  = int(os.getenv('FLASK_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host=host, port=port, debug=debug)
