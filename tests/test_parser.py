"""Tests for QFX parser — bank detection and field extraction."""

import pytest

from app.parser import parse_qfx

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SCOTIABANK_QFX = b"""OFXHEADER:100
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
<FITID>20240115001</FITID>
<NAME>TIM HORTONS #1234</NAME>
<MEMO>Coffee</MEMO>
</STMTTRN>
<STMTTRN>
<TRNTYPE>CREDIT</TRNTYPE>
<DTPOSTED>20240101</DTPOSTED>
<TRNAMT>2500.00</TRNAMT>
<FITID>20240101001</FITID>
<NAME>DIRECT DEPOSIT PAYROLL</NAME>
</STMTTRN>
</BANKTRANLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>"""

BMO_QFX = b"""OFXHEADER:100
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
<ACCTID>1111222233</ACCTID>
<ACCTTYPE>SAVINGS</ACCTTYPE>
</BANKACCTFROM>
<BANKTRANLIST>
<DTSTART>20240101</DTSTART>
<DTEND>20240131</DTEND>
<STMTTRN>
<TRNTYPE>DEBIT</TRNTYPE>
<DTPOSTED>20240110</DTPOSTED>
<TRNAMT>-120.00</TRNAMT>
<FITID>BMO20240110001</FITID>
<NAME>HYDRO ONE</NAME>
</STMTTRN>
</BANKTRANLIST>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>"""


# ---------------------------------------------------------------------------
# Bank detection
# ---------------------------------------------------------------------------


def test_detects_scotiabank():
    parsed = parse_qfx(SCOTIABANK_QFX)
    assert parsed.bank == "scotiabank"


def test_detects_bmo():
    parsed = parse_qfx(BMO_QFX)
    assert parsed.bank == "bmo"


def test_bank_hint_overrides_detection():
    # Even though the file says Scotiabank, the hint forces bmo
    parsed = parse_qfx(SCOTIABANK_QFX, bank_hint="bmo")
    assert parsed.bank == "bmo"


# ---------------------------------------------------------------------------
# Account metadata
# ---------------------------------------------------------------------------


def test_account_number_extracted():
    parsed = parse_qfx(SCOTIABANK_QFX)
    assert parsed.account_number == "9876543210"


def test_account_type_extracted():
    parsed = parse_qfx(SCOTIABANK_QFX)
    assert parsed.account_type == "CHECKING"


# ---------------------------------------------------------------------------
# Transaction fields
# ---------------------------------------------------------------------------


def test_transaction_count():
    parsed = parse_qfx(SCOTIABANK_QFX)
    assert len(parsed.transactions) == 2


def test_transaction_amount_negative():
    parsed = parse_qfx(SCOTIABANK_QFX)
    debit = next(t for t in parsed.transactions if t.fitid == "20240115001")
    assert debit.amount == pytest.approx(-45.67)


def test_transaction_amount_positive():
    parsed = parse_qfx(SCOTIABANK_QFX)
    credit = next(t for t in parsed.transactions if t.fitid == "20240101001")
    assert credit.amount == pytest.approx(2500.00)


def test_transaction_description():
    parsed = parse_qfx(SCOTIABANK_QFX)
    debit = next(t for t in parsed.transactions if t.fitid == "20240115001")
    assert "TIM HORTONS" in debit.description


def test_transaction_fitid():
    parsed = parse_qfx(SCOTIABANK_QFX)
    fitids = {t.fitid for t in parsed.transactions}
    assert "20240115001" in fitids
    assert "20240101001" in fitids


def test_transaction_date():
    from datetime import date

    parsed = parse_qfx(SCOTIABANK_QFX)
    debit = next(t for t in parsed.transactions if t.fitid == "20240115001")
    assert debit.date == date(2024, 1, 15)
