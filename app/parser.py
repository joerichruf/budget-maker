"""
QFX parser for Scotiabank and BMO exports.
Returns a normalised dict ready for the importer.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import ofxparse

BankName = Literal["scotiabank", "bmo", "unknown"]

# Map substrings found in FI>ORG or FI>FID to our bank names
_BANK_SIGNATURES: list[tuple[str, BankName]] = [
    ("scotia", "scotiabank"),
    ("0832", "scotiabank"),
    ("bmo", "bmo"),
    ("bank of montreal", "bmo"),
    ("0001", "bmo"),
]


@dataclass
class ParsedTransaction:
    fitid: str
    date: date
    amount: float
    description: str
    memo: str | None


@dataclass
class ParsedFile:
    bank: BankName
    account_number: str | None
    account_type: str | None
    transactions: list[ParsedTransaction] = field(default_factory=list)


def _detect_bank(ofx: ofxparse.OfxParser) -> BankName:
    """Try to detect the bank from FI metadata in the QFX file."""
    try:
        fi_org = (ofx.account.institution.organization or "").lower()
        fi_fid = (ofx.account.institution.fid or "").lower()
        combined = fi_org + " " + fi_fid
    except AttributeError:
        combined = ""

    for signature, bank in _BANK_SIGNATURES:
        if signature in combined:
            return bank

    return "unknown"


def parse_qfx(file_bytes: bytes, bank_hint: BankName | None = None) -> ParsedFile:
    """
    Parse a QFX file (bytes) and return a ParsedFile.

    bank_hint: manually specified bank to override auto-detection.
    """
    ofx = ofxparse.OfxParser.parse(io.BytesIO(file_bytes))

    bank: BankName = bank_hint or _detect_bank(ofx)

    try:
        account_number = ofx.account.account_id
        account_type = ofx.account.account_type
    except AttributeError:
        account_number = None
        account_type = None

    transactions: list[ParsedTransaction] = []
    for txn in ofx.account.statement.transactions:
        description = (getattr(txn, "payee", None) or getattr(txn, "id", "")).strip()
        memo = (getattr(txn, "memo", None) or "").strip() or None

        # Some banks put the useful name in memo when payee is a code
        if not description and memo:
            description, memo = memo, None

        transactions.append(
            ParsedTransaction(
                fitid=txn.id,
                date=txn.date.date() if hasattr(txn.date, "date") else txn.date,
                amount=float(txn.amount),
                description=description or "N/A",
                memo=memo,
            )
        )

    return ParsedFile(
        bank=bank,
        account_number=account_number,
        account_type=account_type,
        transactions=transactions,
    )
