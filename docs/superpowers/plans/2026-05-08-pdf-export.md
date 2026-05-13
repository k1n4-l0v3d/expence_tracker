# PDF Monthly Report Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a one-page PDF monthly report (summary cards + SVG donut chart + category table) exportable from the profile page using WeasyPrint.

**Architecture:** Pure-Python SVG donut chart injected into a standalone Jinja2 HTML template; WeasyPrint converts HTML+CSS to PDF server-side. WeasyPrint is imported with a try/except fallback so the app starts even without system libraries. Template is created before route tests to satisfy `render_template` inside the mocked route test.

**Tech Stack:** WeasyPrint, Python `math`, Jinja2, Flask `Response`, Bootstrap 5 (profile button only).

---

## File Map

| File | Action | Content |
|------|--------|---------|
| `requirements.txt` | Modify | Add `weasyprint` |
| `nixpacks.toml` | Create | Railway system packages |
| `app.py` | Modify | `import math`; `import weasyprint` (try/except); `_svg_donut()`, `_build_pdf_context()`, `_render_pdf()`; route `profile_export_pdf` |
| `templates/pdf/monthly_report.html` | Create | Standalone PDF template |
| `static/css/pdf_report.css` | Create | Print-ready A4 CSS |
| `templates/profile.html` | Modify | PDF button + JS |
| `tests/test_pdf_export.py` | Create | 4 tests |

---

## Task 1: Install WeasyPrint and create nixpacks.toml

**Files:**
- Modify: `requirements.txt`
- Create: `nixpacks.toml`

- [ ] **Step 1: Add weasyprint to requirements.txt**

Open `requirements.txt` and append:

```
weasyprint
```

- [ ] **Step 2: Create nixpacks.toml**

Create `/Users/k1n4_l0v3d/Desktop/expence_tracker-main/nixpacks.toml`:

```toml
[phases.setup]
nixPkgs = ["pango", "harfbuzz", "gdk-pixbuf", "cairo", "fontconfig", "freetype", "libffi"]
```

- [ ] **Step 3: Install weasyprint locally**

```bash
cd /Users/k1n4_l0v3d/Desktop/expence_tracker-main
source venv/bin/activate
pip install weasyprint
```

Expected: `Successfully installed weasyprint-...` (plus dependencies like cssselect2, tinycss2, etc.)

- [ ] **Step 4: Verify import works**

```bash
source venv/bin/activate
python -c "import weasyprint; print('weasyprint OK')"
```

Expected: `weasyprint OK`

- [ ] **Step 5: Commit**

```bash
git add requirements.txt nixpacks.toml
git commit -m "feat: add weasyprint dependency and nixpacks.toml for Railway"
```

---

## Task 2: `_svg_donut` function + tests

**Files:**
- Modify: `app.py` — after `_RU_MONTH_NAMES` constant (≈ line 2402)
- Create: `tests/test_pdf_export.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_pdf_export.py`:

```python
import pytest
from app import app as flask_app, db, User


def _register_and_login(client, username='pdfuser', password='pass1234'):
    client.post('/register', data={
        'username': username, 'email': f'{username}@example.com',
        'password': password, 'confirm': password,
    }, follow_redirects=True)
    client.post('/login', data={'login': username, 'password': password},
                follow_redirects=True)


def test_svg_donut_two_segments():
    """_svg_donut with two segments returns valid SVG with path elements."""
    from app import _svg_donut
    result = _svg_donut([
        {'color': '#4361ee', 'value': 500.0, 'label': 'Еда'},
        {'color': '#e8115b', 'value': 300.0, 'label': 'Кафе'},
    ])
    assert '<svg' in result
    assert '<path' in result
    assert '#4361ee' in result
    assert '#e8115b' in result


def test_svg_donut_empty_returns_circle():
    """_svg_donut with no segments returns grey circle fallback."""
    from app import _svg_donut
    result = _svg_donut([])
    assert '<svg' in result
    assert '<circle' in result
    assert '<path' not in result


def test_pdf_route_requires_month(client):
    """GET /profile/export/pdf with month=0 redirects to profile."""
    _register_and_login(client)
    resp = client.get('/profile/export/pdf?year=2026&month=0',
                      follow_redirects=False)
    assert resp.status_code == 302
    assert '/profile' in resp.headers['Location']


def test_pdf_route_returns_pdf(client):
    """GET /profile/export/pdf with valid month returns PDF content-type."""
    from unittest.mock import patch, MagicMock
    _register_and_login(client)
    mock_html = MagicMock()
    mock_html.write_pdf.return_value = b'%PDF-1.4 fake'
    with patch('app.weasyprint.HTML', return_value=mock_html):
        resp = client.get('/profile/export/pdf?year=2026&month=5')
    assert resp.status_code == 200
    assert resp.content_type == 'application/pdf'
    assert resp.data == b'%PDF-1.4 fake'
```

- [ ] **Step 2: Run to verify they fail**

```bash
source venv/bin/activate
pytest tests/test_pdf_export.py -v 2>&1 | tail -10
```

Expected: 4 FAILED — `ImportError: cannot import name '_svg_donut'`

- [ ] **Step 3: Add `import math` and weasyprint import to `app.py`**

In `app.py`, find the imports block. After `import calendar`, add:

```python
import math
```

After `import openpyxl` (near the end of imports), add:

```python
try:
    import weasyprint
except Exception:
    weasyprint = None
```

- [ ] **Step 4: Add `_svg_donut` to `app.py`**

After the `_RU_MONTH_NAMES` constant (≈ line 2406), add:

```python
def _svg_donut(segments: list) -> str:
    """Return an SVG donut chart string for the given segments."""
    R, r, cx, cy = 90, 55, 100, 100
    total = sum(s['value'] for s in segments if s['value'] > 0)

    if not segments or total == 0:
        return (
            f'<svg viewBox="0 0 200 200" width="180" height="180" '
            f'xmlns="http://www.w3.org/2000/svg">'
            f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="#e9ecef"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="white"/>'
            f'</svg>'
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
        f'<svg viewBox="0 0 200 200" width="180" height="180" '
        f'xmlns="http://www.w3.org/2000/svg">'
        + ''.join(paths) +
        f'</svg>'
    )
```

- [ ] **Step 5: Run SVG tests**

```bash
pytest tests/test_pdf_export.py::test_svg_donut_two_segments tests/test_pdf_export.py::test_svg_donut_empty_returns_circle -v 2>&1 | tail -8
```

Expected: 2 PASSED

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_pdf_export.py
git commit -m "feat: add _svg_donut function and PDF export tests"
```

---

## Task 3: HTML template and CSS

**Files:**
- Create: `templates/pdf/monthly_report.html`
- Create: `static/css/pdf_report.css`

*(Template must exist before route tests run in Task 4, since render_template is called before the WeasyPrint mock.)*

- [ ] **Step 1: Create template directory and HTML file**

Create `/Users/k1n4_l0v3d/Desktop/expence_tracker-main/templates/pdf/monthly_report.html`:

```html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <link rel="stylesheet" href="{{ url_for('static', filename='css/pdf_report.css') }}">
</head>
<body>
  <div class="page">

    <header class="report-header">
      <span class="app-name">Трекер расходов</span>
      <span class="report-title">{{ username }} • {{ month_name }} {{ year }}</span>
    </header>

    <div class="summary-row">
      <div class="card card-income">
        <div class="card-label">Доходы</div>
        <div class="card-value">{{ "%.0f"|format(income) }} ₽</div>
      </div>
      <div class="card card-expense">
        <div class="card-label">Расходы</div>
        <div class="card-value">{{ "%.0f"|format(expenses) }} ₽</div>
      </div>
      <div class="card card-balance">
        <div class="card-label">Остаток</div>
        <div class="card-value">{{ "%.0f"|format(balance) }} ₽</div>
      </div>
    </div>

    <div class="chart-row">
      <div class="chart-col">{{ svg_chart|safe }}</div>
      <div class="table-col">
        <table class="cat-table">
          {% for cat in categories %}
          <tr>
            <td class="dot-cell"><span class="dot" style="background:{{ cat.color }}"></span></td>
            <td class="name-cell">{{ cat.name }}</td>
            <td class="pct-cell">{{ "%.1f"|format(cat.pct) }}%</td>
            <td class="amt-cell">{{ "%.0f"|format(cat.total) }} ₽</td>
          </tr>
          {% endfor %}
          {% if not categories %}
          <tr><td colspan="4" style="text-align:center;color:#888;padding:4mm">Расходов нет</td></tr>
          {% endif %}
        </table>
      </div>
    </div>

    <footer class="report-footer">
      Сгенерировано {{ generated }}
    </footer>

  </div>
</body>
</html>
```

- [ ] **Step 2: Create CSS file**

Create `/Users/k1n4_l0v3d/Desktop/expence_tracker-main/static/css/pdf_report.css`:

```css
@page {
    size: A4;
    margin: 15mm 20mm;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: "DejaVu Sans", Arial, sans-serif;
    font-size: 10pt;
    color: #1a1a2e;
}

.page { width: 100%; }

/* Header */
.report-header {
    background: linear-gradient(135deg, #4361ee, #e8115b);
    color: #fff;
    padding: 8mm 10mm;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-radius: 4mm;
    margin-bottom: 6mm;
    -weasy-flex-direction: row;
}
.app-name    { font-size: 14pt; font-weight: 700; letter-spacing: 0.5pt; }
.report-title { font-size: 11pt; opacity: 0.9; }

/* Summary cards */
.summary-row {
    display: flex;
    gap: 4mm;
    margin-bottom: 6mm;
}
.card {
    flex: 1;
    border-radius: 3mm;
    padding: 4mm 5mm;
    text-align: center;
}
.card-income  { background: #e8f5e9; }
.card-expense { background: #fce4ec; }
.card-balance { background: #e3f2fd; }
.card-label { font-size: 8pt; color: #555; margin-bottom: 1mm; }
.card-value { font-size: 14pt; font-weight: 700; }
.card-income  .card-value { color: #2e7d32; }
.card-expense .card-value { color: #c62828; }
.card-balance .card-value { color: #1565c0; }

/* Chart + table */
.chart-row {
    display: flex;
    gap: 6mm;
    align-items: flex-start;
    margin-bottom: 6mm;
}
.chart-col { width: 55mm; flex-shrink: 0; }
.chart-col svg { width: 100%; height: auto; }
.table-col { flex: 1; }

/* Category table */
.cat-table { width: 100%; border-collapse: collapse; }
.cat-table tr { border-bottom: 0.3mm solid #e9ecef; }
.cat-table td { padding: 1.5mm 2mm; font-size: 9pt; vertical-align: middle; }
.dot-cell  { width: 5mm; }
.dot { display: inline-block; width: 3mm; height: 3mm; border-radius: 50%; }
.pct-cell  { text-align: right; color: #666; width: 14mm; }
.amt-cell  { text-align: right; font-weight: 600; width: 22mm; }

/* Footer */
.report-footer {
    border-top: 0.3mm solid #dee2e6;
    padding-top: 3mm;
    font-size: 7pt;
    color: #888;
    text-align: center;
}
```

- [ ] **Step 3: Verify template syntax**

```bash
source venv/bin/activate
python -c "
from app import app
with app.app_context():
    src = open('templates/pdf/monthly_report.html').read()
    app.jinja_env.parse(src)
    print('Template syntax OK')
"
```

Expected: `Template syntax OK`

- [ ] **Step 4: Commit**

```bash
git add templates/pdf/monthly_report.html static/css/pdf_report.css
git commit -m "feat: add PDF report HTML template and CSS"
```

---

## Task 4: `_build_pdf_context`, `_render_pdf`, and route

**Files:**
- Modify: `app.py` — after `_svg_donut` function

- [ ] **Step 1: Add `_build_pdf_context`, `_render_pdf`, and route to `app.py`**

After `_svg_donut`, add:

```python
def _build_pdf_context(user_id: int, year: int, month: int) -> dict:
    summary   = get_monthly_summary(user_id, year, month)
    income    = get_monthly_income(user_id, year, month)
    total_exp = 0.0
    cats      = []

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
```

Find the line `@app.route('/profile/import', methods=['POST'])` (≈ line 740) and insert the new route BEFORE it:

```python
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
```

- [ ] **Step 2: Run all PDF export tests**

```bash
source venv/bin/activate
pytest tests/test_pdf_export.py -v 2>&1 | tail -12
```

Expected: 4 PASSED

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -q 2>&1 | tail -4
```

Expected: 98 passed (94 existing + 4 new)

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: add _build_pdf_context, _render_pdf, and profile_export_pdf route"
```

---

## Task 5: Profile button + JS

**Files:**
- Modify: `templates/profile.html` (≈ line 181 — after the Excel submit button)

- [ ] **Step 1: Add PDF button to export form**

Find the export form submit button (≈ line 181):

```html
                    <button type="submit" class="btn btn-outline-success btn-sm">
                        <i class="bi bi-download me-1"></i>Скачать Excel
                    </button>
                </form>
```

Replace with:

```html
                    <button type="submit" class="btn btn-outline-success btn-sm">
                        <i class="bi bi-download me-1"></i>Скачать Excel
                    </button>
                    <a id="pdfExportBtn"
                       href="#"
                       class="btn btn-danger btn-sm disabled"
                       aria-disabled="true"
                       title="Выберите месяц для PDF">
                        <i class="bi bi-file-earmark-pdf me-1"></i>PDF
                    </a>
                </form>
                <script>
                (function () {
                    var pdfBtn   = document.getElementById('pdfExportBtn');
                    if (!pdfBtn) return;
                    var form     = pdfBtn.closest('form');
                    var yearSel  = form ? form.querySelector('[name="year"]')  : null;
                    var monthSel = form ? form.querySelector('[name="month"]') : null;
                    if (!yearSel || !monthSel) return;
                    var base = "{{ url_for('profile_export_pdf') }}";

                    function updatePdf() {
                        var m = parseInt(monthSel.value, 10);
                        if (m >= 1 && m <= 12) {
                            pdfBtn.href = base + '?year=' + yearSel.value + '&month=' + m;
                            pdfBtn.removeAttribute('aria-disabled');
                            pdfBtn.classList.remove('disabled');
                        } else {
                            pdfBtn.href = '#';
                            pdfBtn.setAttribute('aria-disabled', 'true');
                            pdfBtn.classList.add('disabled');
                        }
                    }

                    yearSel.addEventListener('change', updatePdf);
                    monthSel.addEventListener('change', updatePdf);
                    updatePdf();
                })();
                </script>
```

- [ ] **Step 2: Verify Jinja syntax**

```bash
source venv/bin/activate
python -c "
from app import app
with app.app_context():
    src = open('templates/profile.html').read()
    app.jinja_env.parse(src)
    print('Template syntax OK')
"
```

Expected: `Template syntax OK`

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -q 2>&1 | tail -4
```

Expected: 98 passed, 0 failed

- [ ] **Step 4: Commit**

```bash
git add templates/profile.html
git commit -m "feat: add PDF export button with JS to profile page"
```

---

## Task 6: Final check and push

- [ ] **Step 1: Verify app imports cleanly**

```bash
source venv/bin/activate
python -c "from app import app, _svg_donut, _build_pdf_context, _render_pdf, profile_export_pdf; print('All OK')"
```

Expected: `All OK`

- [ ] **Step 2: Run full test suite**

```bash
pytest tests/ -v 2>&1 | grep -E "PASSED|FAILED|ERROR" | tail -20
```

Expected: all PASSED, 0 FAILED

- [ ] **Step 3: Push to GitHub**

```bash
git push origin main
```
