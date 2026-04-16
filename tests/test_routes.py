"""
Integration tests for the FastAPI routes.
Uses TestClient with a per-test in-memory DB injected via dependency override.
"""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Category, Transaction

# Minimal valid Scotiabank QFX for upload tests
_SCOTIABANK_QFX = b"""OFXHEADER:100
DATA:OFXSGML
VERSION:151
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE

<OFX>
<SIGNONMSGSRSV1>
<SONRS>
<STATUS><CODE>0</CODE><SEVERITY>INFO</SEVERITY></STATUS>
<DTSERVER>20240115</DTSERVER>
<LANGUAGE>ENG</LANGUAGE>
<FI><ORG>Scotiabank</ORG><FID>0832</FID></FI>
</SONRS>
</SIGNONMSGSRSV1>
<BANKMSGSRSV1>
<STMTTRNRS>
<TRNUID>1</TRNUID>
<STATUS><CODE>0</CODE><SEVERITY>INFO</SEVERITY></STATUS>
<STMTRS>
<CURDEF>CAD</CURDEF>
<BANKACCTFROM>
<BANKID>0832</BANKID>
<ACCTID>9876543210</ACCTID>
<ACCTTYPE>CHECKING</ACCTTYPE>
</BANKACCTFROM>
<BANKTRANLIST>
<DTSTART>20240101</DTSTART>
<DTEND>20240131</DTEND>
<STMTTRN>
<TRNTYPE>DEBIT</TRNTYPE>
<DTPOSTED>20240115</DTPOSTED>
<TRNAMT>-45.67</TRNAMT>
<FITID>RT-001</FITID>
<NAME>TIM HORTONS #1234</NAME>
</STMTTRN>
<STMTTRN>
<TRNTYPE>CREDIT</TRNTYPE>
<DTPOSTED>20240101</DTPOSTED>
<TRNAMT>2500.00</TRNAMT>
<FITID>RT-002</FITID>
<NAME>DIRECT DEPOSIT PAYROLL</NAME>
</STMTTRN>
</BANKTRANLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>"""


@pytest.fixture
def client(db):
    """TestClient with get_db overridden to use the in-memory test DB."""
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Import page
# ---------------------------------------------------------------------------


def test_import_page_loads(client):
    resp = client.get("/import")
    assert resp.status_code == 200
    assert "Import QFX" in resp.text


def test_import_post_success(client, db):
    resp = client.post(
        "/import",
        files={"file": ("export.qfx", _SCOTIABANK_QFX, "application/octet-stream")},
        data={"bank_hint": "auto"},
    )
    assert resp.status_code == 200
    assert "2" in resp.text  # "2 transaction(s) imported"
    assert "scotiabank" in resp.text

    # Verify transactions actually landed in the DB
    assert db.query(Transaction).count() == 2


def test_import_post_dedup(client, db):
    payload = {
        "files": {"file": ("export.qfx", _SCOTIABANK_QFX, "application/octet-stream")},
        "data": {"bank_hint": "auto"},
    }
    client.post("/import", **payload)
    resp = client.post("/import", **payload)
    assert resp.status_code == 200
    assert "2" in resp.text  # "2 duplicate(s) skipped"
    assert db.query(Transaction).count() == 2


def test_import_post_bad_file_returns_error(client):
    resp = client.post(
        "/import",
        files={"file": ("bad.qfx", b"not valid qfx data", "application/octet-stream")},
        data={"bank_hint": "auto"},
    )
    assert resp.status_code == 200
    assert "Failed to parse" in resp.text or "Error" in resp.text


def test_import_post_with_bank_hint(client, db):
    resp = client.post(
        "/import",
        files={"file": ("export.qfx", _SCOTIABANK_QFX, "application/octet-stream")},
        data={"bank_hint": "scotiabank"},
    )
    assert resp.status_code == 200
    assert db.query(Transaction).count() == 2


# ---------------------------------------------------------------------------
# Transaction list
# ---------------------------------------------------------------------------


def test_transaction_list_empty(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "No transactions found" in resp.text


def test_transaction_list_shows_imported(client, db):
    client.post(
        "/import",
        files={"file": ("export.qfx", _SCOTIABANK_QFX, "application/octet-stream")},
        data={"bank_hint": "auto"},
    )
    resp = client.get("/")
    assert resp.status_code == 200
    assert "TIM HORTONS" in resp.text
    assert "DIRECT DEPOSIT" in resp.text


def test_transaction_list_filter_by_bank(client, db):
    client.post(
        "/import",
        files={"file": ("export.qfx", _SCOTIABANK_QFX, "application/octet-stream")},
        data={"bank_hint": "auto"},
    )
    resp = client.get("/?bank=bmo")
    assert resp.status_code == 200
    # No BMO transactions were imported — table should be empty
    assert "No transactions found" in resp.text


def test_transaction_list_filter_by_month(client, db):
    client.post(
        "/import",
        files={"file": ("export.qfx", _SCOTIABANK_QFX, "application/octet-stream")},
        data={"bank_hint": "auto"},
    )
    resp = client.get("/?month=2024-01")
    assert resp.status_code == 200
    assert "TIM HORTONS" in resp.text


def test_transaction_list_filter_by_category(client, db):
    client.post(
        "/import",
        files={"file": ("export.qfx", _SCOTIABANK_QFX, "application/octet-stream")},
        data={"bank_hint": "auto"},
    )
    income_cat = db.query(Category).filter_by(name="Income").first()
    resp = client.get(f"/?category_id={income_cat.id}")
    assert resp.status_code == 200
    assert "DIRECT DEPOSIT" in resp.text
    assert "TIM HORTONS" not in resp.text


# ---------------------------------------------------------------------------
# Category update
# ---------------------------------------------------------------------------


def test_update_category(client, db):
    client.post(
        "/import",
        files={"file": ("export.qfx", _SCOTIABANK_QFX, "application/octet-stream")},
        data={"bank_hint": "auto"},
    )
    txn = db.query(Transaction).filter(Transaction.fitid == "RT-001").first()
    shopping = db.query(Category).filter_by(name="Shopping").first()

    resp = client.post(
        f"/transactions/{txn.id}/category",
        data={"category_id": shopping.id},
    )
    # Should redirect back to /
    assert resp.status_code == 200

    db.refresh(txn)
    assert txn.category_id == shopping.id
    assert txn.is_manual_category is True


def test_update_category_invalid_txn(client):
    """Updating a non-existent transaction should not raise — just do nothing."""
    resp = client.post("/transactions/99999/category", data={"category_id": 1})
    assert resp.status_code == 200
