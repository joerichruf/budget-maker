# Budget Maker

A self-hosted budget tracker for Canadian bank exports (Scotiabank & BMO).
Import QFX files, auto-categorize transactions, and view your spending in one place.

---

## Quick start (Docker)

```bash
git clone <repo-url>
cd budget-maker
docker compose up --build
```

te

Open [http://localhost:8000](http://localhost:8000), then go to **Import** to upload your first QFX file.

Data is persisted in `./data/budget.db` on the host via a volume mount.

---

## Developer setup

### Prerequisites

- Python 3.11+
- Git

### 1. Clone and create a virtual environment

```bash
git clone <repo-url>
cd budget-maker
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dev dependencies

```bash
pip install -r requirements-dev.txt
```

### 3. Install pre-commit hooks

```bash
pre-commit install
```

Hooks run automatically on every `git commit`. To run them manually against all files:

```bash
pre-commit run --all-files
```

### 4. Run the app locally

```bash
DATABASE_URL=sqlite:///./data/budget.db uvicorn app.main:app --reload
```

Open [http://localhost:8000](http://localhost:8000).

---

## Running tests

```bash
pytest
```

With coverage report:

```bash
pytest --cov=app --cov-report=html
open reports/htmlcov/index.html   # macOS
xdg-open reports/htmlcov/index.html  # Linux
```

---

## Project structure

```
budget-maker/
├── app/
│   ├── main.py            # FastAPI app entry point
│   ├── database.py        # SQLAlchemy engine + session
│   ├── models.py          # ORM models (Transaction, Category, …)
│   ├── parser.py          # QFX → ParsedFile
│   ├── importer.py        # ParsedFile → DB with dedup
│   ├── categorizer.py     # Keyword-rule matching engine
│   ├── seed.py            # Default categories + 134 keyword rules
│   ├── routers/
│   │   ├── imports.py     # GET/POST /import
│   │   └── transactions.py# GET / and POST /transactions/{id}/category
│   ├── templates/         # Jinja2 HTML templates
│   └── static/css/        # Custom CSS
├── tests/                 # Pytest test suite
├── .github/workflows/     # GitHub Actions CI
├── .pre-commit-config.yaml
├── ruff.toml
├── pytest.ini
├── requirements.txt       # Runtime dependencies
├── requirements-dev.txt   # + dev/test dependencies
├── Dockerfile
└── docker-compose.yml
```

---

## CI / GitHub Actions

Every push and pull request to `main` runs three jobs:

| Job | What it does |
|---|---|
| **pre-commit** | ruff lint + format, trailing whitespace, YAML check |
| **pytest** | Full test suite with ≥ 70% coverage gate |
| **docker** | Builds the Docker image to catch Dockerfile regressions |

### Artifacts (free, 30-day retention)

After each CI run the following are uploaded as GitHub Actions artifacts:

- **`coverage-report`** — HTML coverage report (`reports/htmlcov/`)
- **`junit-results`** — JUnit XML test results (`reports/junit.xml`)

Download them from the **Actions** tab → select a run → **Artifacts** section.

### Docker image storage

To also push built images to the **GitHub Container Registry** (`ghcr.io`) — free for public repos, included in the GitHub free plan for private repos — add this to the `docker` job after the build step:

```yaml
- name: Log in to GHCR
  uses: docker/login-action@v3
  with:
    registry: ghcr.io
    username: ${{ github.actor }}
    password: ${{ secrets.GITHUB_TOKEN }}

- name: Push image
  uses: docker/build-push-action@v5
  with:
    context: .
    push: true
    tags: ghcr.io/${{ github.repository }}:latest
```

---

## Supported banks

| Bank | Format | Auto-detected |
|---|---|---|
| Scotiabank | QFX | Yes (ORG: Scotiabank / FID: 0832) |
| BMO | QFX | Yes (ORG: BMO / FID: 0001) |

If auto-detection fails, select the bank manually in the import form.

---

## Phases

- **Phase 1** ✅ — QFX import, dedup, auto-categorize, transaction list UI
- **Phase 2** — Category rule management UI (add/edit/delete keyword rules)
- **Phase 3** — Dashboard with spending graphs by category and month
- **Phase 4** — Drag-and-drop import, CSV export
