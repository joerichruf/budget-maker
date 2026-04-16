"""Tests for the auto-categorization engine."""

import pytest

from app.categorizer import categorize
from app.models import CategorizationRule, Category


def _cat_name(db, cat_id):
    if cat_id is None:
        return None
    return db.query(Category).filter_by(id=cat_id).first().name


# ---------------------------------------------------------------------------
# Default rules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "description,expected_category",
    [
        ("TIM HORTONS #1234", "Restaurants & Coffee"),
        ("STARBUCKS STORE 999", "Restaurants & Coffee"),
        ("MCDONALD'S #5678", "Restaurants & Coffee"),
        ("DOORDASH*ORDER", "Restaurants & Coffee"),
        ("UBER EATS TORONTO", "Restaurants & Coffee"),
        ("LOBLAWS #0042", "Groceries"),
        ("SOBEYS EXTRA", "Groceries"),
        ("NO FRILLS STORE", "Groceries"),
        ("PETRO-CANADA GAS", "Transportation"),
        ("ESSO STATION 12", "Transportation"),
        ("PRESTO FARE PAYMENT", "Transportation"),
        ("NETFLIX.COM", "Entertainment"),
        ("SPOTIFY PREMIUM", "Entertainment"),
        ("DISNEY+ MONTHLY", "Entertainment"),
        ("AMAZON PRIME", "Entertainment"),  # higher priority than amazon→Shopping
        ("HYDRO ONE NETWORKS", "Utilities"),
        ("ROGERS WIRELESS", "Utilities"),
        ("BELL CANADA", "Utilities"),
        ("SHOPPERS DRUG MART", "Health"),
        ("REXALL PHARMACY", "Health"),
        ("AIR CANADA", "Travel"),
        ("WESTJET AIRLINES", "Travel"),
        ("AIRBNB RESERVATION", "Travel"),
        ("DIRECT DEPOSIT PAYROLL", "Income"),
        ("MANULIFE INSURANCE", "Financial"),
    ],
)
def test_default_rule_match(db, description, expected_category):
    cat_id = categorize(description, db)
    assert _cat_name(db, cat_id) == expected_category


# ---------------------------------------------------------------------------
# Priority — more specific pattern wins over generic
# ---------------------------------------------------------------------------


def test_uber_eats_beats_uber(db):
    """'uber eats' (priority 10) must win over 'uber' (priority 5)."""
    cat_id = categorize("UBER EATS*ORDER 123", db)
    assert _cat_name(db, cat_id) == "Restaurants & Coffee"


def test_amazon_prime_beats_amazon(db):
    """'amazon prime' (priority 10) must win over 'amazon' (priority 5)."""
    cat_id = categorize("AMAZON PRIME MEMBERSHIP", db)
    assert _cat_name(db, cat_id) == "Entertainment"


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------


def test_unknown_merchant_returns_other(db):
    cat_id = categorize("XYZZY TOTALLY UNKNOWN 99999", db)
    assert _cat_name(db, cat_id) == "Other"


def test_case_insensitive_match(db):
    cat_id = categorize("tim hortons downtown", db)
    assert _cat_name(db, cat_id) == "Restaurants & Coffee"


# ---------------------------------------------------------------------------
# Custom rules
# ---------------------------------------------------------------------------


def test_custom_rule_takes_effect(db):
    groceries_id = db.query(Category).filter_by(name="Groceries").first().id
    db.add(
        CategorizationRule(
            pattern="MY LOCAL MARKET", category_id=groceries_id, priority=10
        )
    )
    db.commit()

    cat_id = categorize("MY LOCAL MARKET PURCHASE", db)
    assert _cat_name(db, cat_id) == "Groceries"


def test_higher_priority_custom_rule_wins(db):
    restaurants_id = (
        db.query(Category).filter_by(name="Restaurants & Coffee").first().id
    )
    shopping_id = db.query(Category).filter_by(name="Shopping").first().id

    # Add two rules for the same keyword — higher priority should win
    db.add(
        CategorizationRule(pattern="ACME STORE", category_id=shopping_id, priority=5)
    )
    db.add(
        CategorizationRule(
            pattern="ACME STORE", category_id=restaurants_id, priority=15
        )
    )
    db.commit()

    cat_id = categorize("ACME STORE PURCHASE", db)
    assert _cat_name(db, cat_id) == "Restaurants & Coffee"
