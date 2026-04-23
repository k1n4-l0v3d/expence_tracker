# Clear All Data — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Очистить все данные" button to the profile page that permanently deletes all expenses, incomes, and budget records for the current user after modal confirmation.

**Architecture:** One new Flask route `POST /profile/clear-data` inserted after `profile_import` in `app.py`. A "Опасная зона" card added to the right column in `templates/profile.html` and a confirmation modal added to `{% block modals %}`.

**Tech Stack:** Flask 3.1, SQLAlchemy, Bootstrap 5.3, Jinja2, CSRF via Flask-WTF.

---

## Files

- Modify: `app.py` — insert route after line 859 (after `profile_import` return statement, before admin section)
- Modify: `templates/profile.html` — add card before `{% endblock %}` at line 182, add modal inside `{% block modals %}` before `{% endblock %}` at line 234

---

### Task 1: Backend route `POST /profile/clear-data`

**Files:**
- Modify: `app.py` — insert after line 859

- [ ] **Step 1: Insert the route**

Find this comment in `app.py`:
```python
# ─── Администраторская панель ──────────────────────────────────────────────────
```

Insert the following block immediately before it:

```python
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


```

- [ ] **Step 2: Verify syntax**

```bash
python3 -c "import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add POST /profile/clear-data route"
```

---

### Task 2: UI — "Опасная зона" card and modal

**Files:**
- Modify: `templates/profile.html`

- [ ] **Step 1: Add the "Опасная зона" card**

In `templates/profile.html`, find the closing tags of the right column — the block that ends with the Excel import form and then `</div></div>{% endblock %}`:

```html
                    <div class="text-muted small mt-1">Только .xlsx, максимум 5 МБ</div>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

Replace with:

```html
                    <div class="text-muted small mt-1">Только .xlsx, максимум 5 МБ</div>
                </form>
            </div>
        </div>

        <!-- Опасная зона -->
        <div class="card shadow-sm border-0 mt-4" style="border-color:var(--bs-danger-border-subtle)!important;border:1px solid">
            <div class="card-header border-0 fw-semibold pt-3 text-danger">
                <i class="bi bi-exclamation-triangle me-2"></i>Опасная зона
            </div>
            <div class="card-body">
                <p class="text-muted small mb-3">
                    Расходы, доходы и бюджет за всё время будут удалены безвозвратно.
                    Категории сохранятся.
                </p>
                <button type="button" class="btn btn-outline-danger btn-sm"
                        data-bs-toggle="modal" data-bs-target="#clearDataModal">
                    <i class="bi bi-trash me-1"></i>Очистить все данные
                </button>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Add the confirmation modal**

In `templates/profile.html`, find the end of `{% block modals %}` — just before the final `{% endblock %}` after the avatarModal closing `</div>`:

```html
</div>
{% endblock %}

{% block scripts %}
```

Insert the modal before `{% endblock %}`:

```html
</div>

<!-- Модал подтверждения очистки данных -->
<div class="modal fade" id="clearDataModal" tabindex="-1">
    <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
            <div class="modal-header border-0 pb-0">
                <h6 class="modal-title fw-semibold text-danger">
                    <i class="bi bi-exclamation-triangle me-2"></i>Удалить все данные?
                </h6>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
                Это действие <strong>необратимо</strong>. Все расходы, доходы и бюджет
                будут удалены навсегда. Категории останутся.
            </div>
            <div class="modal-footer border-0 pt-0">
                <button type="button" class="btn btn-outline-secondary btn-sm"
                        data-bs-dismiss="modal">Отмена</button>
                <form method="POST" action="{{ url_for('profile_clear_data') }}" class="d-inline">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <button type="submit" class="btn btn-danger btn-sm">
                        <i class="bi bi-trash me-1"></i>Удалить всё
                    </button>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
```

- [ ] **Step 3: Verify page renders**

Run `python3 app.py`, open `http://localhost:5001/profile`.
- "Опасная зона" card appears below the "Данные" card
- Click "Очистить все данные" → modal opens with warning text
- "Отмена" closes modal
- "Удалить всё" submits and redirects back to profile with flash warning

- [ ] **Step 4: Commit**

```bash
git add templates/profile.html
git commit -m "feat: add clear data UI card and confirmation modal to profile"
```
