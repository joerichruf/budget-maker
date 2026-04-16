"""Tests for the import pipeline — deduplication and account creation."""

from datetime import date

import pytest

from app.importer import import_parsed_file
from app.models import Account, Transaction
from app.parser import ParsedFile, ParsedTransaction


def _make_file(transactions, bank="scotiabank", account="ACC001"):
    return ParsedFile(
        bank=bank,
        account_number=account,
        account_type="CHECKING",
        transactions=transactions,
    )


def _txn(fitid, amount=-10.00, description="SOME STORE", txn_date=date(2024, 1, 15)):
    return ParsedTransaction(
        fitid=fitid,
        date=txn_date,
        amount=amount,
        description=description,
        memo=None,
    )


# ---------------------------------------------------------------------------
# Basic import
# ---------------------------------------------------------------------------


def test_imports_transactions(db):
    parsed = _make_file([_txn("001"), _txn("002")])
    result = import_parsed_file(parsed, db)
    assert result.imported == 2
    assert result.duplicates == 0


def test_transactions_stored_in_db(db):
    parsed = _make_file([_txn("001", amount=-99.99, description="LOBLAWS")])
    import_parsed_file(parsed, db)
    txn = db.query(Transaction).filter_by(fitid="001").first()
    assert txn is not None
    assert txn.amount == pytest.approx(-99.99)
    assert txn.description == "LOBLAWS"


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def test_no_duplicate_on_reimport(db):
    parsed = _make_file([_txn("001"), _txn("002")])
    import_parsed_file(parsed, db)
    result = import_parsed_file(parsed, db)  # same file again
    assert result.imported == 0
    assert result.duplicates == 2


def test_same_fitid_different_bank_not_duplicate(db):
    """FITID uniqueness is scoped per bank — same FITID from two banks is valid."""
    scotia = _make_file([_txn("SHARED-001")], bank="scotiabank")
    bmo = _make_file([_txn("SHARED-001")], bank="bmo")
    r1 = import_parsed_file(scotia, db)
    r2 = import_parsed_file(bmo, db)
    assert r1.imported == 1
    assert r2.imported == 1


def test_partial_reimport_skips_existing(db):
    """Only new transactions should be imported when re-importing an expanded file."""
    first = _make_file([_txn("001"), _txn("002")])
    import_parsed_file(first, db)

    second = _make_file([_txn("001"), _txn("002"), _txn("003")])
    result = import_parsed_file(second, db)
    assert result.imported == 1
    assert result.duplicates == 2


# ---------------------------------------------------------------------------
# Account creation
# ---------------------------------------------------------------------------


def test_account_created_on_first_import(db):
    parsed = _make_file([_txn("001")], bank="scotiabank", account="SC-9876")
    import_parsed_file(parsed, db)
    account = (
        db.query(Account).filter_by(bank="scotiabank", account_number="SC-9876").first()
    )
    assert account is not None


def test_account_reused_on_reimport(db):
    parsed = _make_file([_txn("001")], bank="bmo", account="BM-1234")
    import_parsed_file(parsed, db)
    parsed2 = _make_file([_txn("002")], bank="bmo", account="BM-1234")
    import_parsed_file(parsed2, db)
    count = db.query(Account).filter_by(bank="bmo", account_number="BM-1234").count()
    assert count == 1


# ---------------------------------------------------------------------------
# Auto-categorization during import
# ---------------------------------------------------------------------------


def test_imported_transaction_auto_categorized(db):
    parsed = _make_file([_txn("001", description="TIM HORTONS #99")])
    import_parsed_file(parsed, db)
    txn = db.query(Transaction).filter_by(fitid="001").first()
    assert txn.category is not None
    assert txn.category.name == "Restaurants & Coffee"
    assert txn.is_manual_category is False


def test_unknown_transaction_falls_back_to_other(db):
    parsed = _make_file([_txn("001", description="XYZZY UNKNOWN MERCHANT 99999")])
    import_parsed_file(parsed, db)
    txn = db.query(Transaction).filter_by(fitid="001").first()
    assert txn.category is not None
    assert txn.category.name == "Other"
