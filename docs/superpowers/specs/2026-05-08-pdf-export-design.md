# PDF Monthly Report Export — Design Spec

**Date:** 2026-05-08
**Status:** Approved

---

## Problem

The app exports data to Excel only. Users want a clean, printable one-page PDF summary for personal archive or accounting — showing income/expenses summary cards, a donut chart by category, and a category breakdown table.

## Solution

New route `GET /profile/export/pdf?year=Y&month=M` renders a Jinja2 HTML template to PDF using WeasyPrint. The donut chart is a pure-SVG string generated in Python (no matplotlib). The export button is placed in the existing "Данные" card on the profile page, next to the Excel button.

---

## Layout (single A4 page)

```
┌─────────────────────────────────────┐
│  ТРЕКЕР РАСХОДОВ    Иван • Май 2026 │  ← gradient header
├─────────────────────────────────────┤
│  [Доходы]   [Расходы]   [Остаток]   │  ← 3 summary cards
├──────────────┬──────────────────────┤
│              │  Еда        12 400 ₽ │
│  SVG donut   │  Транспорт   8 200 ₽ │  ← chart + category table
│              │  Кафе        6 100 ₽ │
│              │  ...                 │
├─────────────────────────────────────┤
│  Сгенерировано 08.05.2026  стр. 1   │  ← footer
└─────────────────────────────────────┘
```

---

## New Files

| File | Purpose |
|------|---------|
| `templates/pdf/monthly_report.html` | Standalone Jinja2 template (no base.html) |
| `static/css/pdf_report.css` | Print-ready CSS (A4, mm units) |
| `nixpacks.toml` | Railway system package config for WeasyPrint |
| `tests/test_pdf_export.py` | Unit + integration tests |

## Modified Files

| File | Change |
|------|--------|
| `app.py` | Add `import weasyprint` at top; add `_svg_donut()`, `_build_pdf_context()`, `_render_pdf()`, route `profile_export_pdf` |
| `requirements.txt` | Add `weasyprint` |
| `templates/profile.html` | Add PDF button + JS next to Excel button |

---

## Backend (`app.py`)

### `_svg_donut(segments: list[dict]) -> str`

```python
# segments = [{'color': '#4361ee', 'value': 12400.0, 'label': 'Еда'}, ...]
# Returns an SVG string with a donut chart.
```

- Canvas: `viewBox="0 0 200 200"`, `width="180" height="180"`
- Outer radius: 90, inner radius: 55 (hole), center: (100, 100)
- Uses `math.cos` / `math.sin` to compute arc endpoints
- Each segment is a `<path>` with `fill=color` using SVG arc commands (`M`, `A`, `L`)
- Segments drawn clockwise from top (−π/2)
- If total == 0: renders a single grey circle
- No text labels on the chart itself (legend is in the HTML table)

Arc path formula for a segment spanning angle `start_rad` to `end_rad`:
```
x1, y1 = outer arc start
x2, y2 = outer arc end
x3, y3 = inner arc end
x4, y4 = inner arc start
large_arc = 1 if sweep > π else 0
path = f"M {x1} {y1} A 90 90 0 {large_arc} 1 {x2} {y2}
         L {x3} {y3} A 55 55 0 {large_arc} 0 {x4} {y4} Z"
```

### `_build_pdf_context(user_id: int, year: int, month: int) -> dict`

```python
{
    'username':   current_user.username,
    'year':       year,
    'month':      month,
    'month_name': _RU_MONTH_NAMES[month],        # existing constant
    'generated':  date.today().strftime('%d.%m.%Y'),
    'income':     float,                          # get_monthly_income()
    'expenses':   float,                          # sum of summary totals
    'balance':    float,
    'categories': [                               # sorted by total desc, only > 0
        {'name': str, 'color': str, 'total': float, 'pct': float}
    ],
    'svg_chart':  str,                            # _svg_donut() result
}
```

### `_render_pdf(user_id: int, year: int, month: int) -> bytes`

```python
ctx  = _build_pdf_context(user_id, year, month)
html = render_template('pdf/monthly_report.html', **ctx)
return weasyprint.HTML(string=html, base_url=request.host_url).write_pdf()
```

`base_url` is needed so WeasyPrint can resolve the CSS file URL.

### Route `GET /profile/export/pdf`

```python
@app.route('/profile/export/pdf')
@login_required
@ban_check
def profile_export_pdf():
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

---

## Template (`templates/pdf/monthly_report.html`)

Standalone HTML — no `{% extends %}`. Loads only `pdf_report.css`.

```html
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <link rel="stylesheet" href="{{ url_for('static', filename='css/pdf_report.css') }}">
</head>
<body>
  <div class="page">
    <!-- Header -->
    <header class="report-header">
      <span class="app-name">Трекер расходов</span>
      <span class="report-title">{{ username }} • {{ month_name }} {{ year }}</span>
    </header>

    <!-- Summary cards -->
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

    <!-- Chart + categories -->
    <div class="chart-row">
      <div class="chart-col">{{ svg_chart|safe }}</div>
      <div class="table-col">
        <table class="cat-table">
          {% for cat in categories %}
          <tr>
            <td class="dot-cell">
              <span class="dot" style="background:{{ cat.color }}"></span>
            </td>
            <td class="name-cell">{{ cat.name }}</td>
            <td class="pct-cell">{{ cat.pct|round(1) }}%</td>
            <td class="amt-cell">{{ "%.0f"|format(cat.total) }} ₽</td>
          </tr>
          {% endfor %}
        </table>
      </div>
    </div>

    <!-- Footer -->
    <footer class="report-footer">
      Сгенерировано {{ generated }}
    </footer>
  </div>
</body>
</html>
```

---

## CSS (`static/css/pdf_report.css`)

```css
@page {
    size: A4;
    margin: 15mm 20mm;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: "DejaVu Sans", Arial, sans-serif; font-size: 10pt; color: #1a1a2e; }

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
}
.app-name   { font-size: 14pt; font-weight: 700; letter-spacing: 0.5pt; }
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

/* Chart + table row */
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
.dot       { display: inline-block; width: 3mm; height: 3mm; border-radius: 50%; }
.name-cell { }
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

---

## Profile Button (`templates/profile.html`)

The profile page is at `/profile` with no query params — month/year live inside the export form selects, not in the URL. So the PDF button uses JavaScript to read the current select values and update its `href` dynamically.

Add inside the existing export form (after the Excel submit button):

```html
<a id="pdfExportBtn"
   href="#"
   class="btn btn-danger btn-sm"
   title="Выберите месяц для PDF">
    <i class="bi bi-file-earmark-pdf me-1"></i>PDF
</a>
```

Add a `<script>` block after the form:

```javascript
(function () {
    var yearSel  = document.querySelector('[name="year"]');
    var monthSel = document.querySelector('[name="month"]');
    var pdfBtn   = document.getElementById('pdfExportBtn');
    var base     = "{{ url_for('profile_export_pdf') }}";

    function updatePdf() {
        var m = parseInt(monthSel.value);
        if (m && m >= 1 && m <= 12) {
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
    updatePdf(); // set initial state
})();
```

---

## Deployment (`nixpacks.toml`)

New file in project root:

```toml
[phases.setup]
nixPkgs = ["pango", "harfbuzz", "gdk-pixbuf", "cairo", "fontconfig", "freetype", "libffi"]
```

WeasyPrint requires these system libraries. Without them the PDF route will raise `OSError` on import.

---

## Tests (`tests/test_pdf_export.py`)

Three tests, WeasyPrint mocked to avoid system dependency in CI:

```python
def test_svg_donut_generates_valid_svg():
    # Direct unit test — no mock needed
    from app import _svg_donut
    with flask_app.app_context():
        result = _svg_donut([
            {'color': '#4361ee', 'value': 500.0, 'label': 'Еда'},
            {'color': '#e8115b', 'value': 300.0, 'label': 'Кафе'},
        ])
    assert '<svg' in result
    assert '<path' in result

def test_svg_donut_empty_segments():
    from app import _svg_donut
    with flask_app.app_context():
        result = _svg_donut([])
    assert '<svg' in result  # grey circle fallback

def test_pdf_route_requires_month(client):
    # month=0 → redirect with flash
    _register_and_login(client)
    resp = client.get('/profile/export/pdf?year=2026&month=0',
                      follow_redirects=False)
    assert resp.status_code == 302

def test_pdf_route_returns_pdf(client):
    # month specified → PDF response (WeasyPrint mocked)
    from unittest.mock import patch, MagicMock
    _register_and_login(client)
    mock_pdf = MagicMock()
    mock_pdf.write_pdf.return_value = b'%PDF-fake'
    with patch('app.weasyprint.HTML', return_value=mock_pdf):
        resp = client.get('/profile/export/pdf?year=2026&month=5')
    assert resp.status_code == 200
    assert resp.content_type == 'application/pdf'
```

---

## Out of Scope

- PDF for full year (only specific month)
- Expense list table in PDF (compact layout only)
- Dark mode PDF variant
- Email delivery of PDF
- Custom branding / logo upload
