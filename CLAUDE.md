# Budget Maker — Claude Guide

## Project overview

FastAPI + SQLAlchemy (SQLite) backend with Jinja2 server-rendered templates.
No React/Vue — all UI is Jinja2 + Pico CSS + Chart.js. Small JS snippets are fine when they genuinely improve UX.

## Dev setup

The app runs in Docker; tests and linting run in a local venv.

```bash
# Run the app
docker compose up

# Install dev dependencies (one-time)
pip install -r requirements-dev.txt
```

App is available at http://localhost:8080.

## Commands

```bash
# Tests (must pass before a task is done)
pytest tests/

# Lint + format (runs ruff check --fix, ruff-format, and general hooks)
pre-commit run --all-files

# Individual lint/format checks
ruff check app/ tests/
ruff format app/ tests/
```

## Before marking a task complete

Always run both:
1. `pytest tests/` — all tests must pass, coverage must stay ≥ 70%
2. `pre-commit run --all-files` — no lint or format errors

## Architecture

```
app/
  main.py            # FastAPI app, router registration, DB init/seed on startup
  models.py          # SQLAlchemy ORM: Account, Category, CategorizationRule, Transaction
  database.py        # Engine + get_db dependency
  seed.py            # 11 default categories + 134 auto-categorization rules
  categorizer.py     # Substring rule matching (case-insensitive, priority-ordered)
  parser.py          # QFX file parser (Scotiabank + BMO via ofxparse)
  importer.py        # Import with dedup: primary key on (fitid, bank)
  routers/
    transactions.py  # GET / (list+filter+sort), POST /transactions/{id}/category, GET /dashboard
    imports.py       # GET/POST /import
  templates/         # Jinja2 — transactions.html, dashboard.html, import.html, base.html
  static/css/app.css # Custom styles on top of Pico CSS
```

## Key conventions

- **Filters are GET params** — all transaction filters (`category_id`, `bank`, `month`, `account_type`, `sort`, `order`) live in the URL query string so they're bookmarkable and preserved on pagination.
- **Category update preserves filters** — `POST /transactions/{id}/category` redirects to `Referer` so the user stays on their filtered view.
- **Multi-category filter** — `category_id` is `list[int] = Query(default=[])`, the form uses `<select multiple>`.
- **Auto-categorization runs on import** — never on manual category changes (`is_manual_category = True` marks user overrides).
- **No Alembic** — schema is created from models on startup via `Base.metadata.create_all`. Any model change drops and recreates in dev (SQLite). Be explicit with the user before changing models.
- **Seed data** — `seed.py` runs on every startup but is idempotent. Editing the 134 rules in `seed.py` affects all new imports but not already-categorized transactions.

## Testing

- Tests use an in-memory SQLite DB seeded with default categories (see `tests/conftest.py`).
- `TestClient` follows redirects by default — POST endpoints that redirect will resolve to the final page.
- Add tests for any new route or filter parameter.
