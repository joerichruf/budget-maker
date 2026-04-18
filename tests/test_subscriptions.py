from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Account, Category, Transaction
from app.routers.subscriptions import detect_subscriptions


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def account(db):
    a = Account(bank="scotiabank", account_number="SUB-001", account_type="CHECKING")
    db.add(a)
    db.flush()
    return a


def _add_monthly(db, account, cat, desc, amount, start_date, n=3):
    """Add n monthly transactions starting from start_date."""
    for i in range(n):
        db.add(
            Transaction(
                fitid=f"SUB-{desc}-{i}",
                bank="scotiabank",
                account_id=account.id,
                date=start_date + timedelta(days=30 * i),
                amount=amount,
                description=desc,
                category_id=cat.id,
            )
        )
    db.commit()


# ── GET /subscriptions ────────────────────────────────────────────────────────


def test_subscriptions_empty(client):
    resp = client.get("/subscriptions")
    assert resp.status_code == 200
    assert "No recurring subscriptions" in resp.text


def test_subscriptions_detects_monthly(client, db, account):
    cat = db.query(Category).filter_by(name="Entertainment").first()
    today = date.today()
    start = date(today.year - 1, today.month, 1)
    _add_monthly(db, account, cat, "NETFLIX.COM", -17.99, start, n=4)

    resp = client.get("/subscriptions")
    assert resp.status_code == 200
    assert "NETFLIX.COM" in resp.text
    assert "monthly" in resp.text.lower()
    assert "17.99" in resp.text


def test_subscriptions_totals_shown(client, db, account):
    cat = db.query(Category).filter_by(name="Entertainment").first()
    today = date.today()
    start = date(today.year - 1, today.month, 1)
    _add_monthly(db, account, cat, "NETFLIX.COM", -17.99, start, n=4)

    resp = client.get("/subscriptions")
    assert resp.status_code == 200
    assert "Monthly total" in resp.text
    assert "Annual total" in resp.text


def test_subscriptions_forgotten_flag(client, db, account):
    cat = db.query(Category).filter_by(name="Entertainment").first()
    # Last charge was >60 days ago
    old_start = date.today() - timedelta(days=150)
    _add_monthly(db, account, cat, "OLD.SERVICE", -9.99, old_start, n=3)

    resp = client.get("/subscriptions")
    assert resp.status_code == 200
    assert "Forgotten" in resp.text


def test_subscriptions_active_recent(client, db, account):
    cat = db.query(Category).filter_by(name="Entertainment").first()
    # Last charge within 60 days
    start = date.today() - timedelta(days=62)
    _add_monthly(db, account, cat, "SPOTIFY.COM", -10.99, start, n=3)

    resp = client.get("/subscriptions")
    assert resp.status_code == 200
    assert "Active" in resp.text


def test_subscriptions_skips_irregular(db, account):
    cat = db.query(Category).filter_by(name="Groceries").first()
    # Irregular gaps — should not be detected
    for i, gap in enumerate([5, 15, 3, 7]):
        db.add(
            Transaction(
                fitid=f"IRREG-{i}",
                bank="scotiabank",
                account_id=account.id,
                date=date.today() - timedelta(days=sum([5, 15, 3, 7][i:])),
                amount=-20.0,
                description="RANDOM STORE",
                category_id=cat.id,
            )
        )
    db.commit()
    subs = detect_subscriptions(db)
    names = [s["display_name"].upper() for s in subs]
    assert "RANDOM STORE" not in names


def test_subscriptions_skips_high_variance(db, account):
    cat = db.query(Category).filter_by(name="Groceries").first()
    # Monthly cadence but wildly varying amounts (CV > 0.3)
    amounts = [-10.0, -100.0, -5.0, -80.0]
    for i, amt in enumerate(amounts):
        db.add(
            Transaction(
                fitid=f"HIVAR-{i}",
                bank="scotiabank",
                account_id=account.id,
                date=date.today() - timedelta(days=30 * (len(amounts) - i)),
                amount=amt,
                description="VARIABLE CHARGE",
                category_id=cat.id,
            )
        )
    db.commit()
    subs = detect_subscriptions(db)
    names = [s["display_name"].upper() for s in subs]
    assert "VARIABLE CHARGE" not in names
