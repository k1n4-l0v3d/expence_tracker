from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from datetime import date, datetime
from sqlalchemy import extract, func
from functools import wraps
import os

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret')

db           = SQLAlchemy(app)
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
    name        = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    color       = db.Column(db.String(7), nullable=False, default='#6c757d')
    icon        = db.Column(db.String(50), default='bi-wallet2')
    is_active   = db.Column(db.Boolean, nullable=False, default=True)
    created_at  = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    expenses = db.relationship('Expense',       backref='category', lazy=True)
    budgets  = db.relationship('MonthlyBudget', backref='category', lazy=True)


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
        .filter(Category.is_active.is_(True))
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


# ─── Авторизация ──────────────────────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username'].strip()
        email    = request.form['email'].strip().lower()
        password = request.form['password']
        confirm  = request.form['confirm']

        if password != confirm:
            flash('Пароли не совпадают.', 'danger')
        elif User.query.filter_by(username=username).first():
            flash('Имя пользователя уже занято.', 'danger')
        elif User.query.filter_by(email=email).first():
            flash('Email уже зарегистрирован.', 'danger')
        else:
            # Первый пользователь становится администратором
            role = 'admin' if User.query.count() == 0 else 'user'
            user = User(username=username, email=email, role=role)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash(f'Добро пожаловать, {username}!{"  Вы — администратор." if role == "admin" else ""}', 'success')
            return redirect(url_for('index'))
    return render_template('auth/register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            if user.is_banned:
                flash(f'Аккаунт заблокирован. Причина: {user.ban_reason or "не указана"}.', 'danger')
            else:
                login_user(user, remember=request.form.get('remember') == 'on')
                flash(f'Вы вошли как {user.username}.', 'success')
                return redirect(request.args.get('next') or url_for('index'))
        else:
            flash('Неверное имя пользователя или пароль.', 'danger')
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
        recent=recent, year=year, month=month, today=today, months=months_list())


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

    expenses   = query.order_by(Expense.expense_date.desc(), Expense.created_at.desc()).all()
    categories = Category.query.filter_by(is_active=True).order_by(Category.name).all()

    return render_template('expenses/list.html',
        expenses=expenses, categories=categories,
        year=year, month=month, months=months_list(), selected_cat=cat_id)


@app.route('/expenses/add', methods=['GET', 'POST'])
@login_required
@ban_check
def expense_add():
    categories = Category.query.filter_by(is_active=True).order_by(Category.name).all()
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
    categories = Category.query.filter_by(is_active=True).order_by(Category.name).all()
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


@app.route('/budget', methods=['GET', 'POST'])
@login_required
@ban_check
def budget():
    today      = date.today()
    year       = int(request.args.get('year',  today.year))
    month      = int(request.args.get('month', today.month))
    uid        = current_user.id
    categories = Category.query.filter_by(is_active=True).order_by(Category.name).all()
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
            .filter(Category.is_active.is_(True))
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


with app.app_context():
    db.create_all()
    # Добавляем новые колонки если их ещё нет (safe migration)
    with db.engine.connect() as conn:
        from sqlalchemy import text
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar VARCHAR(10) NULL;"
        ))
        conn.commit()

if __name__ == '__main__':
    app.run(debug=False)
