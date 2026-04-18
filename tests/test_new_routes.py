"""
Tests for goals, insights, review, and uncovered transaction paths.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import (
    Account,
    BalanceEntry,
    CategorizationRule,
    Category,
    Goal,
    Transaction,
)


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def txn(db):
    """A single expense transaction with no category (Other)."""
    other = db.query(Category).filter_by(name="Other").first()
    account = Account(bank="scotiabank", account_number="1234", account_type="CHECKING")
    db.add(account)
    db.flush()
    t = Transaction(
        fitid="TEST-001",
        bank="scotiabank",
        account_id=account.id,
        date=date(2024, 1, 15),
        amount=-50.00,
        description="SOME MERCHANT ABC",
        category_id=other.id,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@pytest.fixture
def two_months(db):
    """Two months of transactions (Jan + Feb 2024) for delta / histogram tests."""
    groceries = db.query(Category).filter_by(name="Groceries").first()
    income = db.query(Category).filter_by(name="Income").first()
    account = Account(bank="scotiabank", account_number="9999", account_type="CHECKING")
    db.add(account)
    db.flush()
    rows = [
        Transaction(
            fitid="M1-1",
            bank="scotiabank",
            account_id=account.id,
            date=date(2024, 1, 5),
            amount=-100.0,
            description="LOBLAWS",
            category_id=groceries.id,
        ),
        Transaction(
            fitid="M1-2",
            bank="scotiabank",
            account_id=account.id,
            date=date(2024, 1, 1),
            amount=2000.0,
            description="PAYROLL",
            category_id=income.id,
        ),
        Transaction(
            fitid="M2-1",
            bank="scotiabank",
            account_id=account.id,
            date=date(2024, 2, 5),
            amount=-120.0,
            description="LOBLAWS",
            category_id=groceries.id,
        ),
        Transaction(
            fitid="M2-2",
            bank="scotiabank",
            account_id=account.id,
            date=date(2024, 2, 1),
            amount=2100.0,
            description="PAYROLL",
            category_id=income.id,
        ),
    ]
    db.add_all(rows)
    db.commit()
    return rows


# ── Dashboard ──────────────────────────────────────────────────────────────────


def test_dashboard_empty(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 200


def test_dashboard_with_data(client, two_months):
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "LOBLAWS" in resp.text or "Groceries" in resp.text


def test_dashboard_month_filter(client, two_months):
    resp = client.get("/dashboard?month=2024-01")
    assert resp.status_code == 200


# ── Transaction list — extra filter paths ─────────────────────────────────────


def test_transaction_list_sort_by_amount(client, two_months):
    resp = client.get("/?sort=amount&order=asc")
    assert resp.status_code == 200


def test_transaction_list_sort_by_account_type(client, two_months):
    resp = client.get("/?sort=account_type&order=desc")
    assert resp.status_code == 200


def test_transaction_list_filter_by_account_type(client, two_months):
    resp = client.get("/?account_type=CHECKING")
    assert resp.status_code == 200


def test_transaction_list_month_delta(client, two_months):
    """Filter by month triggers prev-month delta computation."""
    resp = client.get("/?month=2024-02")
    assert resp.status_code == 200


def test_transaction_list_alltime_delta(client, two_months):
    """No month filter → all-time view with prev-month delta from last two months."""
    resp = client.get("/")
    assert resp.status_code == 200


# ── Category update — new category + apply_to_all ─────────────────────────────


def test_update_category_new_name(client, db, txn):
    resp = client.post(
        f"/transactions/{txn.id}/category",
        data={"category_id": txn.category_id, "new_category_name": "Learning"},
    )
    assert resp.status_code == 200
    db.refresh(txn)
    new_cat = db.query(Category).filter_by(name="Learning").first()
    assert new_cat is not None
    assert txn.category_id == new_cat.id


def test_update_category_existing_name(client, db, txn):
    """new_category_name that already exists reuses that category."""
    resp = client.post(
        f"/transactions/{txn.id}/category",
        data={"category_id": txn.category_id, "new_category_name": "Groceries"},
    )
    assert resp.status_code == 200
    db.refresh(txn)
    groceries = db.query(Category).filter_by(name="Groceries").first()
    assert txn.category_id == groceries.id


def test_update_category_apply_to_all(client, db, txn):
    """apply_to_all updates every transaction with the same description + adds rule."""
    # Add a second transaction with the same description
    t2 = Transaction(
        fitid="TEST-002",
        bank="scotiabank",
        account_id=txn.account_id,
        date=date(2024, 2, 1),
        amount=-30.0,
        description=txn.description,
        category_id=txn.category_id,
    )
    db.add(t2)
    db.commit()

    shopping = db.query(Category).filter_by(name="Shopping").first()
    resp = client.post(
        f"/transactions/{txn.id}/category",
        data={"category_id": shopping.id, "apply_to_all": "true"},
    )
    assert resp.status_code == 200

    db.refresh(txn)
    db.refresh(t2)
    assert txn.category_id == shopping.id
    assert t2.category_id == shopping.id

    rule = db.query(CategorizationRule).filter_by(pattern=txn.description).first()
    assert rule is not None
    assert rule.category_id == shopping.id


def test_update_category_apply_to_all_updates_existing_rule(client, db, txn):
    """apply_to_all updates an existing rule rather than inserting a duplicate."""
    other = db.query(Category).filter_by(name="Other").first()
    rule = CategorizationRule(pattern=txn.description, category_id=other.id, priority=5)
    db.add(rule)
    db.commit()

    shopping = db.query(Category).filter_by(name="Shopping").first()
    client.post(
        f"/transactions/{txn.id}/category",
        data={"category_id": shopping.id, "apply_to_all": "true"},
    )
    db.refresh(rule)
    assert rule.category_id == shopping.id


# ── Insights ──────────────────────────────────────────────────────────────────


def test_insights_empty(client):
    resp = client.get("/insights")
    assert resp.status_code == 200


def test_insights_with_data(client, two_months):
    resp = client.get("/insights")
    assert resp.status_code == 200
    assert "Groceries" in resp.text or "LOBLAWS" in resp.text


def test_insights_variance_needs_two_months(client, two_months):
    """Variance section requires ≥2 months per category — just verify it doesn't crash."""
    resp = client.get("/insights")
    assert resp.status_code == 200


# ── Goals ─────────────────────────────────────────────────────────────────────


def test_goals_page_empty(client):
    resp = client.get("/goals")
    assert resp.status_code == 200


def test_goals_page_with_data(client, db, two_months):
    db.add(
        BalanceEntry(
            label="Chequing",
            account_type="CHECKING",
            balance=5000.0,
            as_of_date=date(2024, 2, 1),
        )
    )
    db.add(
        Goal(
            name="Pay off card",
            starting_amount=10000.0,
            target_amount=0.0,
            target_months=12,
        )
    )
    db.commit()
    resp = client.get("/goals")
    assert resp.status_code == 200
    assert "Pay off card" in resp.text
    assert "Chequing" in resp.text


def test_add_balance_entry(client, db):
    resp = client.post(
        "/goals/balance/add",
        data={
            "label": "Scotia Chequing",
            "account_type": "CHECKING",
            "balance": "4500.00",
            "as_of_date": "2024-02-01",
        },
    )
    assert resp.status_code == 200
    assert db.query(BalanceEntry).count() == 1


def test_delete_balance_entry(client, db):
    entry = BalanceEntry(
        label="Test",
        account_type="SAVINGS",
        balance=1000.0,
        as_of_date=date(2024, 1, 1),
    )
    db.add(entry)
    db.commit()
    resp = client.post(f"/goals/balance/{entry.id}/delete")
    assert resp.status_code == 200
    assert db.query(BalanceEntry).count() == 0


def test_add_goal(client, db):
    resp = client.post(
        "/goals/add",
        data={
            "name": "Emergency fund",
            "starting_amount": "500.0",
            "target_amount": "5000.0",
            "target_months": "24",
        },
    )
    assert resp.status_code == 200
    goal = db.query(Goal).filter_by(name="Emergency fund").first()
    assert goal is not None
    assert goal.target_months == 24


def test_delete_goal(client, db):
    goal = Goal(
        name="Old goal", starting_amount=1000.0, target_amount=0.0, target_months=6
    )
    db.add(goal)
    db.commit()
    resp = client.post(f"/goals/{goal.id}/delete")
    assert resp.status_code == 200
    assert db.query(Goal).filter_by(name="Old goal").first() is None


# ── Review ────────────────────────────────────────────────────────────────────


def test_review_page_empty(client):
    resp = client.get("/review")
    assert resp.status_code == 200


def test_review_page_shows_other_transactions(client, db, txn):
    resp = client.get("/review")
    assert resp.status_code == 200
    assert "SOME MERCHANT ABC" in resp.text


def test_review_suggestions_no_api_key(client, monkeypatch):
    """Without an API key the endpoint returns an empty JSON object."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    resp = client.get("/review/suggestions")
    assert resp.status_code == 200
    assert resp.json() == {}


def test_review_apply_single(client, db, txn):
    shopping = db.query(Category).filter_by(name="Shopping").first()
    resp = client.post(
        "/review/apply",
        data={
            "description": txn.description,
            "category_id": shopping.id,
        },
    )
    assert resp.status_code == 200
    db.refresh(txn)
    assert txn.category_id == shopping.id
    rule = db.query(CategorizationRule).filter_by(pattern=txn.description).first()
    assert rule is not None


def test_review_apply_single_updates_existing_rule(client, db, txn):
    other = db.query(Category).filter_by(name="Other").first()
    rule = CategorizationRule(pattern=txn.description, category_id=other.id, priority=5)
    db.add(rule)
    db.commit()

    shopping = db.query(Category).filter_by(name="Shopping").first()
    client.post(
        "/review/apply",
        data={
            "description": txn.description,
            "category_id": shopping.id,
        },
    )
    db.refresh(rule)
    assert rule.category_id == shopping.id


def test_review_apply_batch(client, db, txn):
    entertainment = db.query(Category).filter_by(name="Entertainment").first()
    resp = client.post(
        "/review/apply-batch",
        json={txn.description: entertainment.name},
    )
    assert resp.status_code == 200
    assert resp.json()["applied"] == 1
    db.refresh(txn)
    assert txn.category_id == entertainment.id


def test_review_apply_batch_unknown_category_skipped(client, db, txn):
    original_cat = txn.category_id
    resp = client.post(
        "/review/apply-batch",
        json={txn.description: "NonExistentCategory"},
    )
    assert resp.status_code == 200
    assert resp.json()["applied"] == 0
    db.refresh(txn)
    assert txn.category_id == original_cat


# ── AI categorizer — no-key path ──────────────────────────────────────────────


def test_suggest_categories_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from app.services.categorizer_ai import suggest_categories

    result = suggest_categories(["SOME STORE"])
    assert result == {}
