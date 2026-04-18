import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Account, User

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
<FITID>U-001</FITID>
<NAME>TIM HORTONS #1234</NAME>
</STMTTRN>
<STMTTRN>
<TRNTYPE>CREDIT</TRNTYPE>
<DTPOSTED>20240101</DTPOSTED>
<TRNAMT>2500.00</TRNAMT>
<FITID>U-002</FITID>
<NAME>DIRECT DEPOSIT PAYROLL</NAME>
</STMTTRN>
</BANKTRANLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>"""

_BMO_QFX = b"""OFXHEADER:100
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
<FI><ORG>BMO</ORG><FID>0001</FID></FI>
</SONRS>
</SIGNONMSGSRSV1>
<BANKMSGSRSV1>
<STMTTRNRS>
<TRNUID>1</TRNUID>
<STATUS><CODE>0</CODE><SEVERITY>INFO</SEVERITY></STATUS>
<STMTRS>
<CURDEF>CAD</CURDEF>
<BANKACCTFROM>
<BANKID>0001</BANKID>
<ACCTID>1111111111</ACCTID>
<ACCTTYPE>CHECKING</ACCTTYPE>
</BANKACCTFROM>
<BANKTRANLIST>
<DTSTART>20240101</DTSTART>
<DTEND>20240131</DTEND>
<STMTTRN>
<TRNTYPE>DEBIT</TRNTYPE>
<DTPOSTED>20240110</DTPOSTED>
<TRNAMT>-99.00</TRNAMT>
<FITID>B-001</FITID>
<NAME>GROCERY STORE</NAME>
</STMTTRN>
</BANKTRANLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>"""


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Users page
# ---------------------------------------------------------------------------


def test_users_page_loads(client):
    resp = client.get("/users")
    assert resp.status_code == 200
    assert "Users" in resp.text


def test_users_page_shows_seeded_users(client):
    resp = client.get("/users")
    assert "User 1" in resp.text
    assert "User 2" in resp.text


def test_create_user(client, db):
    resp = client.post("/users", data={"name": "Alice", "color": "#e91e63"})
    assert resp.status_code == 200  # TestClient follows redirect
    assert db.query(User).filter_by(name="Alice").first() is not None


def test_create_user_duplicate_name(client, db):
    client.post("/users", data={"name": "Bob", "color": "#123456"})
    client.post("/users", data={"name": "Bob", "color": "#654321"})
    assert db.query(User).filter_by(name="Bob").count() == 1


def test_delete_user(client, db):
    user = db.query(User).filter_by(name="User 1").first()
    resp = client.post(f"/users/{user.id}/delete")
    assert resp.status_code == 200
    assert db.query(User).filter_by(name="User 1").first() is None


def test_delete_user_unassigns_accounts(client, db):
    user = db.query(User).filter_by(name="User 1").first()
    acct = Account(bank="scotiabank", account_number="TEST001", user_id=user.id)
    db.add(acct)
    db.commit()

    client.post(f"/users/{user.id}/delete")
    db.refresh(acct)
    assert acct.user_id is None


def test_delete_nonexistent_user(client):
    resp = client.post("/users/99999/delete")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Import with user assignment
# ---------------------------------------------------------------------------


def test_import_assigns_user_to_account(client, db):
    user = db.query(User).filter_by(name="User 1").first()
    client.post(
        "/import",
        files={"file": ("export.qfx", _SCOTIABANK_QFX, "application/octet-stream")},
        data={"bank_hint": "auto", "user_id": str(user.id)},
    )
    acct = (
        db.query(Account)
        .filter_by(bank="scotiabank", account_number="9876543210")
        .first()
    )
    assert acct is not None
    assert acct.user_id == user.id


def test_import_without_user_leaves_account_unassigned(client, db):
    client.post(
        "/import",
        files={"file": ("export.qfx", _SCOTIABANK_QFX, "application/octet-stream")},
        data={"bank_hint": "auto", "user_id": "0"},
    )
    acct = (
        db.query(Account)
        .filter_by(bank="scotiabank", account_number="9876543210")
        .first()
    )
    assert acct is not None
    assert acct.user_id is None


# ---------------------------------------------------------------------------
# Transaction list user filter
# ---------------------------------------------------------------------------


def test_transaction_list_user_filter(client, db):
    user1 = db.query(User).filter_by(name="User 1").first()
    user2 = db.query(User).filter_by(name="User 2").first()

    client.post(
        "/import",
        files={"file": ("sc.qfx", _SCOTIABANK_QFX, "application/octet-stream")},
        data={"bank_hint": "auto", "user_id": str(user1.id)},
    )
    client.post(
        "/import",
        files={"file": ("bmo.qfx", _BMO_QFX, "application/octet-stream")},
        data={"bank_hint": "bmo", "user_id": str(user2.id)},
    )

    # Filter to user 1 only — BMO transaction should not appear
    resp = client.get(f"/?user_id={user1.id}")
    assert resp.status_code == 200
    assert "TIM HORTONS" in resp.text
    assert "GROCERY STORE" not in resp.text

    # Filter to user 2 only
    resp2 = client.get(f"/?user_id={user2.id}")
    assert resp2.status_code == 200
    assert "GROCERY STORE" in resp2.text
    assert "TIM HORTONS" not in resp2.text


def test_transaction_list_multiple_user_filter(client, db):
    user1 = db.query(User).filter_by(name="User 1").first()
    user2 = db.query(User).filter_by(name="User 2").first()

    client.post(
        "/import",
        files={"file": ("sc.qfx", _SCOTIABANK_QFX, "application/octet-stream")},
        data={"bank_hint": "auto", "user_id": str(user1.id)},
    )
    client.post(
        "/import",
        files={"file": ("bmo.qfx", _BMO_QFX, "application/octet-stream")},
        data={"bank_hint": "bmo", "user_id": str(user2.id)},
    )

    resp = client.get(f"/?user_id={user1.id}&user_id={user2.id}")
    assert resp.status_code == 200
    assert "TIM HORTONS" in resp.text
    assert "GROCERY STORE" in resp.text


# ---------------------------------------------------------------------------
# Dashboard user filter
# ---------------------------------------------------------------------------


def test_dashboard_loads(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "Dashboard" in resp.text


def test_dashboard_user_filter(client, db):
    user1 = db.query(User).filter_by(name="User 1").first()

    client.post(
        "/import",
        files={"file": ("sc.qfx", _SCOTIABANK_QFX, "application/octet-stream")},
        data={"bank_hint": "auto", "user_id": str(user1.id)},
    )

    resp = client.get(f"/dashboard?user_id={user1.id}")
    assert resp.status_code == 200


def test_dashboard_per_user_sections(client, db):
    user1 = db.query(User).filter_by(name="User 1").first()
    user2 = db.query(User).filter_by(name="User 2").first()

    client.post(
        "/import",
        files={"file": ("sc.qfx", _SCOTIABANK_QFX, "application/octet-stream")},
        data={"bank_hint": "auto", "user_id": str(user1.id)},
    )

    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert user1.name in resp.text
    assert user2.name in resp.text
