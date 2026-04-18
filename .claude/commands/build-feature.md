# Build Feature — Budget Maker

You are an expert Python web developer working on the budget-maker app.
Your task is to build the feature described in the user's request, end-to-end,
silently and completely, without asking questions until fully done.

## Stack

- **Backend:** FastAPI + SQLAlchemy (SQLite, no Alembic — `Base.metadata.create_all` on startup)
- **Templates:** Jinja2, extending `base.html`, styled with Pico CSS + custom `app.css`
- **Charts:** Chart.js (CDN) when data visualization is needed
- **Tests:** pytest + pytest-cov, in-memory SQLite via `conftest.py`, coverage ≥ 70%
- **Quality:** pre-commit (ruff check + ruff format)
- **Dev server:** `docker compose up` → http://localhost:8080
- **No auth, no React, no TypeScript, no Alembic**

## Key conventions (from CLAUDE.md)

- Filters are GET params — bookmarkable URLs
- Multi-value params: `list[int] = Query(default=[])`, never bare `int | None`
- POST endpoints redirect to `Referer` header (preserves filter state)
- Auto-categorization runs on import only; manual overrides set `is_manual_category = True`
- New models: add to `app/models.py` — tables are auto-created on next startup
- Seed data lives in `app/seed.py` (idempotent, runs every startup)
- No comments unless the WHY is non-obvious

---

## Process — follow exactly, in order

### Phase 1 · Requirements analysis

Read the relevant existing files:
- `app/models.py` — understand the current data model
- `app/main.py` — see registered routers
- `app/templates/base.html` — nav links and layout
- `app/static/css/app.css` — existing CSS classes
- Any existing router that the new feature touches

Identify:
1. New models needed (if any)
2. New or modified router endpoints
3. New templates (or modifications to existing ones)
4. New CSS classes needed
5. Test cases to write

Output a concise phase plan (model → router → template → CSS → tests → commit).
Then immediately execute Phase 2 without waiting.

---

### Phase 2 · Model changes (skip if none needed)

Edit `app/models.py`:
- Add new SQLAlchemy model classes
- Add relationships to existing models if needed
- Use `Column(DateTime, default=datetime.utcnow)` for `created_at`
- Add `UniqueConstraint` where duplicates must be prevented

Do NOT create a migration. Tables are created by `Base.metadata.create_all` on startup.

If seed data is needed, add it to `app/seed.py` following the existing idempotent pattern.

---

### Phase 3 · Router

Create or edit the appropriate file in `app/routers/`:

```python
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
```

Rules:
- GET list/detail pages → `response_class=HTMLResponse`, return `templates.TemplateResponse`
- POST mutations → return `RedirectResponse(url=request.headers.get("referer", "/fallback"), status_code=303)`
- Multi-select query params: `param: list[int] = Query(default=[])`
- Never inline SQL — use SQLAlchemy ORM
- Helper functions for repeated query logic (prefix with `_`)

If it's a new router, register it in `app/main.py`:
```python
from app.routers import new_module
app.include_router(new_module.router)
```

---

### Phase 4 · Template

Create `app/templates/<feature>.html` (or edit existing):

```html
{% extends "base.html" %}
{% block title %}Feature Name — Budget Maker{% endblock %}

{% block content %}
<div class="page-header">
  <h2>Feature Name</h2>
</div>
<!-- content -->
{% endblock %}
```

Rules:
- Use Pico CSS semantic HTML — `<article>`, `<details>`, `<summary>` for panels
- Use existing CSS classes before adding new ones (check `app.css`)
- Monetary values: `{{ "%.2f"|format(value) }}`
- Small JS is fine for UX (auto-submit, status updates, fetch calls) — no frameworks
- Forms that mutate data: `method="post"`, action to the POST endpoint
- If adding a nav link, edit `app/templates/base.html`

---

### Phase 5 · CSS

Edit `app/static/css/app.css` only for styles not achievable with Pico CSS alone.

Rules:
- Group new rules under a labelled comment block: `/* ── Feature name ── */`
- Use `var(--pico-*)` CSS variables for colors/borders to support dark mode
- Never use `!important` unless overriding a Pico default that genuinely needs it
- Mobile-first: use `flex-wrap: wrap` and `flex: 1 1 Xpx` for responsive rows

---

### Phase 6 · Tests

Add tests to `tests/test_new_routes.py` (or create a new `tests/test_<feature>.py`).

Follow the existing pattern from `tests/conftest.py` and `tests/test_routes.py`:

```python
@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()
```

Cover:
- Happy path for every GET page (status 200, key content present)
- Happy path for every POST mutation (status 200 after redirect, DB state correct)
- Edge cases: empty state, invalid IDs, missing optional fields
- Any filter or sort parameter added

Do NOT mock the database. Tests use a real in-memory SQLite DB.

---

### Phase 7 · Quality gate

Run in order — fix any failures before proceeding:

```bash
# Tests with coverage
pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=70

# Lint + format
pre-commit run --all-files
```

If coverage drops below 70%, add more tests. If pre-commit fails, fix the issues.
Do not skip hooks or lower the threshold.

---

### Phase 8 · Git commit

```bash
git add <only the relevant files>
git commit -m "<type>: <concise description of what was built>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

Commit types: `feat`, `fix`, `refactor`, `test`, `style`, `chore`.

---

## Mandatory rules

- Never ask questions during execution — infer intent from the codebase
- Never lower `--cov-fail-under` or use `--no-verify`
- Never use Alembic, React, TypeScript, or external auth libraries
- Never add features beyond what was requested
- No TODO comments, no placeholder code — every phase must be fully implemented
- If a model change would break existing data in a real deployment, note it clearly in the commit message
- End with a one-paragraph summary of what was built and any follow-up the user should know about
