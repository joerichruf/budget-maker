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

## Current features

| Feature | Description |
|---|---|
| **QFX Import** | Upload Scotiabank & BMO QFX files; duplicates are skipped automatically |
| **Auto-categorize** | 134 keyword rules map merchants to categories on import |
| **Manual override** | Click any category badge in the table to reassign; optionally apply to all matching transactions |
| **AI Review** | "Ask Claude" button suggests categories for uncategorized transactions in bulk |
| **Dashboard** | Doughnut + histogram charts for spending by category; filter by month |
| **Insights** | Monthly net balance chart, top recurring expenses, top categories, high-variance & spike detection |
| **Budgets** | Set monthly limits per category; progress bars with over-budget and projected-over warnings |
| **Goals** | Payoff & savings goals evaluated against your trailing 3-month average surplus |
| **Account Balances** | Manual balance entries for net-worth tracking |
| **Dark mode** | Sun/moon toggle, persisted to `localStorage` |

---

## Roadmap — features to build

### Tier 1 — Zero-effort, maximum signal

**Subscription Radar**
Auto-detect recurring charges (same merchant, similar amount, monthly/annual cadence). One screen listing all subscriptions with their total cost. Flag ones with no transaction in 60+ days as "forgotten."

**Spending Forecast & Budget Autopilot**
Auto-suggest budget limits from trailing 3-month averages — one click to accept. Mid-month projection bar: "at this pace you'll overspend Dining by $80."

**Month-End Digest**
Auto-generated weekly summary delivered by email or push: biggest change vs last month, categories trending up, net surplus/deficit. No user action required.

---

### Tier 2 — Smart lazy features

**Natural Language Query**
A search box that understands plain English: "how much on food last summer" or "biggest single transaction this year." Backed by the existing Claude integration.

**Emergency Fund Runway**
One prominent number on the dashboard: "You have 2.4 months of expenses saved." Derived from the balance tracker and average monthly spend.

**Cash Flow Calendar**
Visual monthly calendar overlaying income days against expected bill days. Answers "will I go negative before my next paycheque?" — the core anxiety for lazy budgeters.

**Duplicate Charge Detector**
Surface transactions with the same merchant and a similar amount in the same billing window. "You may have been charged twice by Netflix."

---

### Tier 3 — Power features

**Tax Category Export**
Tag categories as tax-deductible, then export a CSV/PDF summary at tax time. "Here are your $3,200 in deductible expenses."

**Savings Rate Meter**
Prominent stat: "You're saving 22% of income." Benchmark against common targets (15%, 20%). Trend over time on the dashboard.

**Net Worth Timeline**
Combine the balance tracker with monthly net cash flow to show a running net worth chart — the most motivating chart in personal finance.

**Merchant Merge**
"TIM HORTONS #1234" and "TIM HORTONS #5678" are the same place. Merge merchants under one canonical name so reports are clean without manual category work.
