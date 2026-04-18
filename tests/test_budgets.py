from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Account, Category, CategoryBudget, Transaction


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def groceries_cat(db):
    return db.query(Category).filter_by(name="Groceries").first()


@pytest.fixture
def budget(db, groceries_cat):
    b = CategoryBudget(category_id=groceries_cat.id, monthly_limit=500.0)
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


@pytest.fixture
def spending(db, groceries_cat):
    """Transactions in the current month for Groceries."""
    today = date.today()
    account = Account(bank="scotiabank", account_number="0001", account_type="CHECKING")
    db.add(account)
    db.flush()
    t = Transaction(
        fitid="BUD-001",
        bank="scotiabank",
        account_id=account.id,
        date=today,
        amount=-200.0,
        description="LOBLAWS",
        category_id=groceries_cat.id,
    )
    db.add(t)
    db.commit()
    return t


# ── GET /budgets ───────────────────────────────────────────────────────────────


def test_budgets_page_empty(client):
    resp = client.get("/budgets")
    assert resp.status_code == 200
    assert "No budgets set" in resp.text


def test_budgets_page_shows_budget(client, budget):
    resp = client.get("/budgets")
    assert resp.status_code == 200
    assert "Groceries" in resp.text
    assert "500.00" in resp.text


def test_budgets_page_shows_spending(client, budget, spending):
    resp = client.get("/budgets")
    assert resp.status_code == 200
    assert "200.00" in resp.text


def test_budgets_page_shows_over(client, db, groceries_cat):
    """When spent > limit the card should reflect over-budget state."""
    b = CategoryBudget(category_id=groceries_cat.id, monthly_limit=50.0)
    db.add(b)
    db.flush()
    today = date.today()
    account = Account(bank="scotiabank", account_number="0002", account_type="CHECKING")
    db.add(account)
    db.flush()
    db.add(
        Transaction(
            fitid="BUD-OVR",
            bank="scotiabank",
            account_id=account.id,
            date=today,
            amount=-200.0,
            description="COSTCO",
            category_id=groceries_cat.id,
        )
    )
    db.commit()
    resp = client.get("/budgets")
    assert resp.status_code == 200
    assert "budget-over" in resp.text


# ── POST /budgets/set ──────────────────────────────────────────────────────────


def test_set_budget_creates(client, db, groceries_cat):
    resp = client.post(
        "/budgets/set",
        data={
            "category_id": groceries_cat.id,
            "monthly_limit": "300.00",
        },
    )
    assert resp.status_code == 200
    b = db.query(CategoryBudget).filter_by(category_id=groceries_cat.id).first()
    assert b is not None
    assert b.monthly_limit == 300.0


def test_set_budget_updates_existing(client, db, budget):
    client.post(
        "/budgets/set",
        data={
            "category_id": budget.category_id,
            "monthly_limit": "750.00",
        },
    )
    db.refresh(budget)
    assert budget.monthly_limit == 750.0


def test_set_budget_only_one_row_per_category(client, db, groceries_cat):
    client.post(
        "/budgets/set", data={"category_id": groceries_cat.id, "monthly_limit": "100"}
    )
    client.post(
        "/budgets/set", data={"category_id": groceries_cat.id, "monthly_limit": "200"}
    )
    assert db.query(CategoryBudget).filter_by(category_id=groceries_cat.id).count() == 1


# ── POST /budgets/{id}/delete ──────────────────────────────────────────────────


def test_delete_budget(client, db, budget):
    resp = client.post(f"/budgets/{budget.id}/delete")
    assert resp.status_code == 200
    assert db.query(CategoryBudget).filter_by(id=budget.id).first() is None


def test_delete_budget_nonexistent(client):
    resp = client.post("/budgets/99999/delete")
    assert resp.status_code == 200


# ── POST /budgets/accept-suggestions ──────────────────────────────────────────


def test_accept_suggestions_creates_budgets(client, db):
    entertainment = db.query(Category).filter_by(name="Entertainment").first()
    groceries = db.query(Category).filter_by(name="Groceries").first()
    resp = client.post(
        "/budgets/accept-suggestions",
        data={
            "category_ids": [entertainment.id, groceries.id],
            "monthly_limits": ["250.00", "400.00"],
        },
    )
    assert resp.status_code == 200
    assert (
        db.query(CategoryBudget).filter_by(category_id=entertainment.id).first()
        is not None
    )
    assert (
        db.query(CategoryBudget).filter_by(category_id=groceries.id).first() is not None
    )


def test_accept_suggestions_empty_is_noop(client):
    resp = client.post("/budgets/accept-suggestions", data={})
    assert resp.status_code == 200


def test_budgets_page_shows_suggestions(client, db):
    """Unbudgeted categories with 3-month history appear as suggestions."""
    entertainment = db.query(Category).filter_by(name="Entertainment").first()
    account = Account(
        bank="scotiabank", account_number="AUTO-1", account_type="CHECKING"
    )
    db.add(account)
    db.flush()
    for mo in [1, 2, 3]:
        db.add(
            Transaction(
                fitid=f"AUTO-{mo}",
                bank="scotiabank",
                account_id=account.id,
                date=date(2024, mo, 15),
                amount=-150.0,
                description="MOVIE TICKET",
                category_id=entertainment.id,
            )
        )
    db.commit()

    resp = client.get("/budgets")
    assert resp.status_code == 200
    assert "Autopilot" in resp.text
