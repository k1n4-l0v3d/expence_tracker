# Edit Custom Category — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users edit the name and color of their custom categories via a pencil button in the existing "Мои категории" list inside the create-category modal.

**Architecture:** The "Мои категории" section already exists inside `#newCategoryModal` in `templates/expenses/form.html` with delete buttons per row. We add a pencil button to each row, a new `#editCategoryModal`, JS functions to open/save edits, and a `PATCH /categories/<cat_id>` Flask route. No changes to the `<select>` element.

**Tech Stack:** Flask 3.1, SQLAlchemy, Bootstrap 5.3, vanilla JS fetch, CSRF meta tag.

---

## Files

- Modify: `app.py` — add `PATCH /categories/<cat_id>` after `category_delete` (line ~1354)
- Modify: `templates/expenses/form.html` — add pencil button to each cat-row, add `#editCategoryModal`, add JS

---

### Task 1: Backend `PATCH /categories/<cat_id>`

**Files:**
- Modify: `app.py` — insert after `category_delete` function, before `# ─── Attachments` comment

- [ ] **Step 1: Add the route**

Find this line in `app.py`:
```python
# ─── Attachments ──────────────────────────────────────────────────────────────
```

Insert immediately before it:

```python
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

    # Уникальность имени среди системных и своих категорий (кроме самой себя)
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


```

- [ ] **Step 2: Verify syntax**

```bash
python3 -c "import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add PATCH /categories/<id> route for editing custom categories"
```

---

### Task 2: Pencil button in "Мои категории" list

**Files:**
- Modify: `templates/expenses/form.html` — lines 164–172 (each `cat-row` div)

- [ ] **Step 1: Add pencil button to each category row**

Find this block in `templates/expenses/form.html`:

```html
          <div class="d-flex align-items-center justify-content-between py-1 gap-2" id="cat-row-{{ cat.id }}">
            <span class="d-flex align-items-center gap-2 text-truncate">
              <span style="width:10px;height:10px;border-radius:50%;background:{{ cat.color }};flex-shrink:0"></span>
              <span class="small text-truncate">{{ cat.name }}</span>
            </span>
            <button type="button" class="btn btn-sm btn-outline-danger py-0 px-1 flex-shrink-0"
                    style="font-size:.7rem"
                    onclick="deleteCategoryRow({{ cat.id }}, this)">✕</button>
          </div>
```

Replace with:

```html
          <div class="d-flex align-items-center justify-content-between py-1 gap-2" id="cat-row-{{ cat.id }}"
               data-cat-name="{{ cat.name }}" data-cat-color="{{ cat.color }}">
            <span class="d-flex align-items-center gap-2 text-truncate">
              <span class="cat-color-dot" style="width:10px;height:10px;border-radius:50%;background:{{ cat.color }};flex-shrink:0"></span>
              <span class="small text-truncate cat-name-label">{{ cat.name }}</span>
            </span>
            <div class="d-flex gap-1 flex-shrink-0">
              <button type="button" class="btn btn-sm btn-outline-secondary py-0 px-1"
                      style="font-size:.7rem" title="Редактировать"
                      onclick="openEditCategory({{ cat.id }}, this.closest('[id^=cat-row]'))">
                <i class="bi bi-pencil"></i>
              </button>
              <button type="button" class="btn btn-sm btn-outline-danger py-0 px-1"
                      style="font-size:.7rem"
                      onclick="deleteCategoryRow({{ cat.id }}, this)">✕</button>
            </div>
          </div>
```

- [ ] **Step 2: Verify template renders without errors**

Run `python3 app.py`, open `http://localhost:5001/expenses/add`.
Open the "✨ + Создать новую" dropdown → «Мои категории» section shows pencil + delete buttons per row.

- [ ] **Step 3: Commit**

```bash
git add templates/expenses/form.html
git commit -m "feat: add edit button to custom category rows in form"
```

---

### Task 3: Edit category modal + JS

**Files:**
- Modify: `templates/expenses/form.html` — add modal to `{% block modals %}`, add JS to `{% block scripts %}`

- [ ] **Step 1: Add `#editCategoryModal` to `{% block modals %}`**

In `templates/expenses/form.html`, find the end of `{% block modals %}` — just before `{% endblock %}` at line 180:

```html
</div>
{% endblock %}
```

Replace with:

```html
</div>

<!-- Модал редактирования категории -->
<div class="modal fade" id="editCategoryModal" tabindex="-1">
  <div class="modal-dialog modal-sm">
    <div class="modal-content">
      <div class="modal-header border-0 pb-0">
        <h6 class="modal-title fw-semibold">✏️ Редактировать категорию</h6>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        <input type="hidden" id="editCatId">
        <div class="mb-3">
          <label class="form-label fw-semibold">Название <span class="text-danger">*</span></label>
          <input type="text" id="editCatName" class="form-control" maxlength="100">
          <div id="editCatError" class="text-danger small mt-1 d-none"></div>
        </div>
        <div class="mb-1">
          <label class="form-label fw-semibold">Цвет</label>
          <div class="d-flex gap-2 flex-wrap">
            {% for color_hex in ['#e74c3c','#e67e22','#f1c40f','#2ecc71','#3498db','#9b59b6','#1abc9c','#95a5a6'] %}
            <div class="edit-color-swatch" data-color="{{ color_hex }}"
                 style="width:28px;height:28px;border-radius:50%;background:{{ color_hex }};cursor:pointer;border:3px solid transparent"
                 onclick="selectEditColor(this)"></div>
            {% endfor %}
          </div>
          <input type="hidden" id="editCatColor" value="#3498db">
        </div>
      </div>
      <div class="modal-footer border-0 pt-0">
        <button type="button" class="btn btn-sm btn-secondary" data-bs-dismiss="modal">Отмена</button>
        <button type="button" id="saveEditCatBtn" class="btn btn-sm grad-primary" onclick="saveEditCategory()">Сохранить</button>
      </div>
    </div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Add JS functions to `{% block scripts %}`**

In `templates/expenses/form.html`, find this line near the end of the `<script>` block (just before the closing `</script>`):

```javascript
}
</script>
{% endblock %}
```

Insert before `</script>`:

```javascript
let _editCatRow = null;

function openEditCategory(catId, rowEl) {
  _editCatRow = rowEl;
  document.getElementById('editCatId').value = catId;
  const name  = rowEl.dataset.catName;
  const color = rowEl.dataset.catColor;
  document.getElementById('editCatName').value  = name;
  document.getElementById('editCatColor').value = color;
  document.getElementById('editCatError').classList.add('d-none');
  document.querySelectorAll('.edit-color-swatch').forEach(s => {
    s.style.border = s.dataset.color === color ? '3px solid white' : '3px solid transparent';
  });
  bootstrap.Modal.getOrCreateInstance(document.getElementById('editCategoryModal')).show();
}

function selectEditColor(el) {
  document.querySelectorAll('.edit-color-swatch').forEach(s => s.style.border = '3px solid transparent');
  el.style.border = '3px solid white';
  document.getElementById('editCatColor').value = el.dataset.color;
}

async function saveEditCategory() {
  const btn    = document.getElementById('saveEditCatBtn');
  const catId  = document.getElementById('editCatId').value;
  const name   = document.getElementById('editCatName').value.trim();
  const color  = document.getElementById('editCatColor').value;
  const errEl  = document.getElementById('editCatError');
  errEl.classList.add('d-none');

  if (!name) {
    errEl.textContent = 'Введите название';
    errEl.classList.remove('d-none');
    return;
  }

  btn.disabled = true;
  try {
    const res  = await fetch(`/categories/${catId}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content},
      body: JSON.stringify({name, color}),
    });
    const data = await res.json();
    if (!res.ok) {
      errEl.textContent = data.error || 'Ошибка';
      errEl.classList.remove('d-none');
      return;
    }

    // Обновить строку в списке «Мои категории»
    if (_editCatRow) {
      _editCatRow.dataset.catName  = data.name;
      _editCatRow.dataset.catColor = data.color;
      _editCatRow.querySelector('.cat-color-dot').style.background = data.color;
      _editCatRow.querySelector('.cat-name-label').textContent     = data.name;
    }

    // Обновить <option> в <select>
    const opt = document.querySelector(`#category_id option[value="${catId}"]`);
    if (opt) opt.textContent = data.name;

    bootstrap.Modal.getInstance(document.getElementById('editCategoryModal')).hide();
  } catch(e) {
    errEl.textContent = 'Ошибка сети';
    errEl.classList.remove('d-none');
  } finally {
    btn.disabled = false;
  }
}
```

- [ ] **Step 3: Verify full flow**

1. Open `http://localhost:5001/expenses/add`
2. Click «✨ + Создать новую категорию...» → модал открывается
3. В разделе «Мои категории» нажми ✏️ → открывается модал редактирования с текущим именем и цветом
4. Измени имя, выбери другой цвет, нажми «Сохранить»
5. Строка в списке обновляется (новое имя, новый цвет точки)
6. Закрой модал создания, посмотри на `<select>` — имя категории обновилось
7. Попробуй ввести имя уже существующей категории → ошибка 409

- [ ] **Step 4: Commit**

```bash
git add templates/expenses/form.html
git commit -m "feat: add edit category modal and JS to expense form"
```
