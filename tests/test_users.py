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


@pytest.fixture
def user1(db):
    u = User(name="Alice", color="#6366f1")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def user2(db):
    u = User(name="Bob", color="#f59e0b")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ---------------------------------------------------------------------------
# Users page
# ---------------------------------------------------------------------------


def test_users_page_loads(client):
    resp = client.get("/users")
    assert resp.status_code == 200
    assert "Users" in resp.text


def test_users_page_shows_created_users(client, user1, user2):
    resp = client.get("/users")
    assert "Alice" in resp.text
    assert "Bob" in resp.text


def test_users_page_empty_state(client):
    resp = client.get("/users")
    assert "No users yet" in resp.text


def test_create_user(client, db):
    resp = client.post("/users", data={"name": "Charlie", "color": "#e91e63"})
    assert resp.status_code == 200
    assert db.query(User).filter_by(name="Charlie").first() is not None


def test_create_user_duplicate_name(client, db, user1):
    client.post("/users", data={"name": "Alice", "color": "#654321"})
    assert db.query(User).filter_by(name="Alice").count() == 1


def test_delete_user(client, db, user1):
    resp = client.post(f"/users/{user1.id}/delete")
    assert resp.status_code == 200
    assert db.query(User).filter_by(name="Alice").first() is None


def test_delete_user_unassigns_accounts(client, db, user1):
    acct = Account(bank="scotiabank", account_number="TEST001", user_id=user1.id)
    db.add(acct)
    db.commit()

    client.post(f"/users/{user1.id}/delete")
    db.refresh(acct)
    assert acct.user_id is None


def test_delete_nonexistent_user(client):
    resp = client.post("/users/99999/delete")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Account assignment
# ---------------------------------------------------------------------------


def test_assign_account_to_user(client, db, user1):
    acct = Account(bank="scotiabank", account_number="ASSIGN01")
    db.add(acct)
    db.commit()

    resp = client.post(f"/accounts/{acct.id}/assign", data={"user_id": str(user1.id)})
    assert resp.status_code == 200
    db.refresh(acct)
    assert acct.user_id == user1.id


def test_unassign_account(client, db, user1):
    acct = Account(bank="scotiabank", account_number="ASSIGN02", user_id=user1.id)
    db.add(acct)
    db.commit()

    client.post(f"/accounts/{acct.id}/assign", data={"user_id": "0"})
    db.refresh(acct)
    assert acct.user_id is None


# ---------------------------------------------------------------------------
# Import with user assignment
# ---------------------------------------------------------------------------


def test_import_assigns_user_to_account(client, db, user1):
    client.post(
        "/import",
        files={"file": ("export.qfx", _SCOTIABANK_QFX, "application/octet-stream")},
        data={"bank_hint": "auto", "user_id": str(user1.id)},
    )
    acct = (
        db.query(Account)
        .filter_by(bank="scotiabank", account_number="9876543210")
        .first()
    )
    assert acct is not None
    assert acct.user_id == user1.id


def test_import_creates_new_user_inline(client, db):
    resp = client.post(
        "/import",
        files={"file": ("export.qfx", _SCOTIABANK_QFX, "application/octet-stream")},
        data={
            "bank_hint": "auto",
            "new_user_name": "Inline User",
            "new_user_color": "#123456",
        },
    )
    assert resp.status_code == 200
    new_user = db.query(User).filter_by(name="Inline User").first()
    assert new_user is not None
    acct = (
        db.query(Account)
        .filter_by(bank="scotiabank", account_number="9876543210")
        .first()
    )
    assert acct.user_id == new_user.id


def test_import_without_user_returns_error(client):
    resp = client.post(
        "/import",
        files={"file": ("export.qfx", _SCOTIABANK_QFX, "application/octet-stream")},
        data={"bank_hint": "auto"},
    )
    assert resp.status_code == 200
    assert "Please select a user" in resp.text


# ---------------------------------------------------------------------------
# Transaction list user filter
# ---------------------------------------------------------------------------


def test_transaction_list_user_filter(client, db, user1, user2):
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

    resp = client.get(f"/?user_id={user1.id}")
    assert resp.status_code == 200
    assert "TIM HORTONS" in resp.text
    assert "GROCERY STORE" not in resp.text

    resp2 = client.get(f"/?user_id={user2.id}")
    assert resp2.status_code == 200
    assert "GROCERY STORE" in resp2.text
    assert "TIM HORTONS" not in resp2.text


def test_transaction_list_multiple_user_filter(client, db, user1, user2):
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


def test_dashboard_user_filter(client, db, user1):
    client.post(
        "/import",
        files={"file": ("sc.qfx", _SCOTIABANK_QFX, "application/octet-stream")},
        data={"bank_hint": "auto", "user_id": str(user1.id)},
    )
    resp = client.get(f"/dashboard?user_id={user1.id}")
    assert resp.status_code == 200
    assert "Dashboard" in resp.text


def test_dashboard_per_user_sections(client, db, user1, user2):
    client.post(
        "/import",
        files={"file": ("sc.qfx", _SCOTIABANK_QFX, "application/octet-stream")},
        data={"bank_hint": "auto", "user_id": str(user1.id)},
    )
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert user1.name in resp.text
    assert user2.name in resp.text
