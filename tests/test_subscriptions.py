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
    """Add n monthly transactions on the same day of month."""
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


def test_subscriptions_shows_billing_day(client, db, account):
    cat = db.query(Category).filter_by(name="Entertainment").first()
    start = date(date.today().year - 1, 3, 15)
    _add_monthly(db, account, cat, "SPOTIFY.COM", -10.99, start, n=4)

    resp = client.get("/subscriptions")
    assert resp.status_code == 200
    assert "of month" in resp.text


def test_subscriptions_shows_next_charge(client, db, account):
    cat = db.query(Category).filter_by(name="Entertainment").first()
    today = date.today()
    # last charge is recent (today - 30d), so next_charge is shown
    start = today - timedelta(days=90)
    _add_monthly(db, account, cat, "HULU.COM", -15.99, start, n=4)

    resp = client.get("/subscriptions")
    assert resp.status_code == 200
    assert str(today.year) in resp.text


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
    old_start = date.today() - timedelta(days=150)
    _add_monthly(db, account, cat, "OLD.SERVICE", -9.99, old_start, n=3)

    resp = client.get("/subscriptions")
    assert resp.status_code == 200
    assert "Forgotten" in resp.text


def test_subscriptions_active_recent(client, db, account):
    cat = db.query(Category).filter_by(name="Entertainment").first()
    start = date.today() - timedelta(days=62)
    _add_monthly(db, account, cat, "SPOTIFY.COM", -10.99, start, n=3)

    resp = client.get("/subscriptions")
    assert resp.status_code == 200
    assert "Active" in resp.text


def test_subscriptions_skips_irregular_gaps(db, account):
    cat = db.query(Category).filter_by(name="Groceries").first()
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
    names = [s["display_name"] for s in subs]
    assert "RANDOM STORE" not in names


def test_subscriptions_skips_different_prices(db, account):
    """Transactions at different prices must not be flagged as subscriptions."""
    cat = db.query(Category).filter_by(name="Groceries").first()
    amounts = [-10.00, -10.50, -10.00, -10.50]
    for i, amt in enumerate(amounts):
        db.add(
            Transaction(
                fitid=f"PRICE-{i}",
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
    names = [s["display_name"] for s in subs]
    assert "VARIABLE CHARGE" not in names


def test_subscriptions_skips_inconsistent_day(db, account):
    """Transactions on wildly different days of month must not be flagged."""
    cat = db.query(Category).filter_by(name="Groceries").first()
    # Days: 1st, 15th, 28th — spread > 3
    days = [1, 15, 28]
    today = date.today()
    for i, d in enumerate(days):
        try:
            charge_date = date(today.year - 1, i + 1, d)
        except ValueError:
            charge_date = date(today.year - 1, i + 1, 1)
        db.add(
            Transaction(
                fitid=f"DAYVARY-{i}",
                bank="scotiabank",
                account_id=account.id,
                date=charge_date,
                amount=-9.99,
                description="SCATTERED CHARGE",
                category_id=cat.id,
            )
        )
    db.commit()
    subs = detect_subscriptions(db)
    names = [s["display_name"] for s in subs]
    assert "SCATTERED CHARGE" not in names
