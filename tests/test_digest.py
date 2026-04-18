from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Account, Category, CategoryBudget, Transaction
from app.routers.digest import build_digest


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def account(db):
    a = Account(bank="scotiabank", account_number="DIG-001", account_type="CHECKING")
    db.add(a)
    db.flush()
    return a


@pytest.fixture
def two_past_months(db, account):
    """Two complete past months: Jan 2024 and Feb 2024."""
    entertainment = db.query(Category).filter_by(name="Entertainment").first()
    groceries = db.query(Category).filter_by(name="Groceries").first()
    income = db.query(Category).filter_by(name="Income").first()

    rows = [
        # Jan 2024
        Transaction(
            fitid="D-J1",
            bank="scotiabank",
            account_id=account.id,
            date=date(2024, 1, 5),
            amount=3000.0,
            description="PAYROLL",
            category_id=income.id,
        ),
        Transaction(
            fitid="D-J2",
            bank="scotiabank",
            account_id=account.id,
            date=date(2024, 1, 10),
            amount=-400.0,
            description="LOBLAWS",
            category_id=groceries.id,
        ),
        Transaction(
            fitid="D-J3",
            bank="scotiabank",
            account_id=account.id,
            date=date(2024, 1, 20),
            amount=-200.0,
            description="CINEMA",
            category_id=entertainment.id,
        ),
        # Feb 2024
        Transaction(
            fitid="D-F1",
            bank="scotiabank",
            account_id=account.id,
            date=date(2024, 2, 5),
            amount=3000.0,
            description="PAYROLL",
            category_id=income.id,
        ),
        Transaction(
            fitid="D-F2",
            bank="scotiabank",
            account_id=account.id,
            date=date(2024, 2, 10),
            amount=-350.0,
            description="LOBLAWS",
            category_id=groceries.id,
        ),
        Transaction(
            fitid="D-F3",
            bank="scotiabank",
            account_id=account.id,
            date=date(2024, 2, 20),
            amount=-300.0,
            description="CINEMA 2",
            category_id=entertainment.id,
        ),
    ]
    for r in rows:
        db.add(r)
    db.commit()
    return rows


# ── GET /digest ───────────────────────────────────────────────────────────────


def test_digest_empty(client):
    resp = client.get("/digest")
    assert resp.status_code == 200
    assert "No completed months" in resp.text


def test_digest_page_renders(client, two_past_months):
    resp = client.get("/digest")
    assert resp.status_code == 200
    assert "Monthly Digest" in resp.text


def test_digest_shows_income_expenses(client, two_past_months):
    resp = client.get("/digest")
    assert resp.status_code == 200
    assert "Income" in resp.text
    assert "Expenses" in resp.text
    assert "3000.00" in resp.text


def test_digest_shows_comparison_delta(client, two_past_months):
    resp = client.get("/digest")
    assert resp.status_code == 200
    # Should show vs label
    assert "vs" in resp.text


def test_digest_shows_category_changes(client, two_past_months):
    resp = client.get("/digest")
    assert resp.status_code == 200
    assert "Biggest increases" in resp.text or "Biggest savings" in resp.text


def test_digest_budget_performance(client, db, account, two_past_months):
    groceries = db.query(Category).filter_by(name="Groceries").first()
    db.add(CategoryBudget(category_id=groceries.id, monthly_limit=300.0))
    db.commit()

    resp = client.get("/digest")
    assert resp.status_code == 200
    assert "Budget performance" in resp.text
    assert "Groceries" in resp.text


# ── POST /digest/send-email ───────────────────────────────────────────────────


def test_send_email_no_smtp(client, two_past_months):
    resp = client.post("/digest/send-email")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "SMTP" in data["message"] or "not configured" in data["message"].lower()


def test_send_email_no_data(client):
    resp = client.post("/digest/send-email")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False


# ── build_digest unit tests ───────────────────────────────────────────────────


def test_build_digest_no_data(db):
    result = build_digest(db)
    assert result["has_data"] is False


def test_build_digest_with_data(db, account, two_past_months):
    result = build_digest(db)
    assert result["has_data"] is True
    assert result["cur"]["income"] == 3000.0
    assert result["cur"]["expenses"] > 0
