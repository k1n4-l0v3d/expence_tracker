# Edit Custom Category — Design Spec

**Goal:** Allow users to edit the name and color of their custom categories directly from the expense form category dropdown.

**Architecture:** Replace the native `<select>` in the expense form with a custom Bootstrap dropdown that shows edit/delete buttons next to user-owned categories. One new `PATCH /categories/<cat_id>` route on the backend. Edit modal reuses the same color swatches as the create modal.

---

## Backend

### `PATCH /categories/<int:cat_id>`

- **Auth:** `@login_required`, `@ban_check`
- **Ownership check:** `category.user_id == current_user.id` → 403 if system category or belongs to another user
- **Request body (JSON):**
  ```json
  {"name": "Новое имя", "color": "#e74c3c"}
  ```
- **Validation:**
  - `name`: non-empty, stripped, ≤ 100 chars
  - `color`: matches `#[0-9a-fA-F]{6}` regex
  - Uniqueness: no other category with same name (case-insensitive) visible to this user (`user_id IS NULL OR user_id == current_user.id`), excluding the category being edited
- **On success:** `db.session.commit()` → `200 {"id": cat.id, "name": cat.name, "color": cat.color}`
- **Errors:** 400 bad input, 403 not owner, 404 not found, 409 name conflict

---

## Frontend — Custom Category Dropdown

The native `<select name="category_id">` is hidden (`display:none`). A custom Bootstrap dropdown renders above it showing all categories with action buttons for user-owned ones.

### Structure (rendered by Jinja2)

```html
<!-- Hidden input that holds the actual form value -->
<input type="hidden" name="category_id" id="category_id_hidden" value="{{ expense.category_id if expense else '' }}" required>

<!-- Custom dropdown trigger -->
<div class="dropdown" id="categoryDropdown">
  <button type="button" class="form-select text-start dropdown-toggle" id="categoryBtn"
          data-bs-toggle="dropdown">
    <span id="categoryLabel">— выберите —</span>
  </button>
  <ul class="dropdown-menu w-100" style="max-height:260px;overflow-y:auto">
    {% for cat in categories %}
    <li>
      <div class="dropdown-item d-flex align-items-center gap-2 pe-1"
           data-cat-id="{{ cat.id }}" data-cat-name="{{ cat.name }}"
           data-cat-color="{{ cat.color }}"
           data-user-owned="{{ 'true' if cat.user_id else 'false' }}"
           onclick="selectCategory(this)">
        <span style="width:10px;height:10px;border-radius:50%;background:{{ cat.color }};flex-shrink:0"></span>
        <span class="flex-grow-1">{{ cat.name }}</span>
        {% if cat.user_id %}
        <button type="button" class="btn btn-sm p-0 ms-1 text-secondary"
                style="line-height:1" title="Редактировать"
                onclick="event.stopPropagation(); openEditCategory({{ cat.id }}, '{{ cat.name }}', '{{ cat.color }}')">
          <i class="bi bi-pencil" style="font-size:.75rem"></i>
        </button>
        <button type="button" class="btn btn-sm p-0 ms-1 text-danger"
                style="line-height:1" title="Удалить"
                onclick="event.stopPropagation(); deleteCategory({{ cat.id }}, this)">
          <i class="bi bi-trash" style="font-size:.75rem"></i>
        </button>
        {% endif %}
      </div>
    </li>
    {% endfor %}
    <li><hr class="dropdown-divider"></li>
    <li>
      <div class="dropdown-item text-primary" style="cursor:pointer"
           onclick="openNewCategoryFromDropdown()">
        ✨ + Создать новую категорию...
      </div>
    </li>
  </ul>
</div>
```

### JavaScript functions

**`selectCategory(el)`** — sets hidden input value and updates button label:
```javascript
function selectCategory(el) {
    document.getElementById('category_id_hidden').value = el.dataset.catId;
    document.getElementById('categoryLabel').textContent = el.dataset.catName;
    bootstrap.Dropdown.getInstance(document.getElementById('categoryDropdown').querySelector('[data-bs-toggle]'))?.hide();
}
```

**`openEditCategory(catId, name, color)`** — populates edit modal and shows it:
```javascript
function openEditCategory(catId, name, color) {
    document.getElementById('editCatId').value = catId;
    document.getElementById('editCatName').value = name;
    document.getElementById('editCatColor').value = color;
    // Highlight correct swatch
    document.querySelectorAll('#editCategoryModal .color-swatch')
        .forEach(s => s.style.border = s.dataset.color === color ? '3px solid white' : '3px solid transparent');
    document.getElementById('editCatError').classList.add('d-none');
    bootstrap.Modal.getOrCreateInstance(document.getElementById('editCategoryModal')).show();
}
```

**`saveEditCategory()`** — PATCHes the API and updates DOM:
```javascript
async function saveEditCategory() {
    const catId = document.getElementById('editCatId').value;
    const name  = document.getElementById('editCatName').value.trim();
    const color = document.getElementById('editCatColor').value;
    const errEl = document.getElementById('editCatError');
    errEl.classList.add('d-none');

    if (!name) { errEl.textContent = 'Введите название'; errEl.classList.remove('d-none'); return; }

    const res  = await fetch(`/categories/${catId}`, {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json',
                  'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content},
        body: JSON.stringify({name, color}),
    });
    const data = await res.json();
    if (!res.ok) { errEl.textContent = data.error || 'Ошибка'; errEl.classList.remove('d-none'); return; }

    // Update dropdown item
    const item = document.querySelector(`[data-cat-id="${catId}"]`);
    if (item) {
        item.dataset.catName  = data.name;
        item.dataset.catColor = data.color;
        item.querySelector('span').style.background = data.color;
        item.querySelector('.flex-grow-1').textContent = data.name;
    }
    // Update label if this category is currently selected
    if (document.getElementById('category_id_hidden').value == catId) {
        document.getElementById('categoryLabel').textContent = data.name;
    }
    bootstrap.Modal.getInstance(document.getElementById('editCategoryModal')).hide();
}
```

### Edit Category Modal (`#editCategoryModal`)

Added to `{% block modals %}` in `templates/expenses/form.html`:

```html
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
            <div class="color-swatch" data-color="{{ color_hex }}"
                 style="width:28px;height:28px;border-radius:50%;background:{{ color_hex }};cursor:pointer;border:3px solid transparent"
                 onclick="selectEditColor(this)"></div>
            {% endfor %}
          </div>
          <input type="hidden" id="editCatColor" value="#3498db">
        </div>
      </div>
      <div class="modal-footer border-0 pt-0">
        <button type="button" class="btn btn-sm btn-secondary" data-bs-dismiss="modal">Отмена</button>
        <button type="button" class="btn btn-sm grad-primary" onclick="saveEditCategory()">Сохранить</button>
      </div>
    </div>
  </div>
</div>
```

---

## Files

- Modify: `app.py` — add `PATCH /categories/<cat_id>` route after `category_add`
- Modify: `templates/expenses/form.html` — replace `<select>` with custom dropdown, add edit modal, add JS
