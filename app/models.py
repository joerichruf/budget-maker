from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    bank = Column(String, nullable=False)  # 'scotiabank' | 'bmo'
    account_number = Column(String)  # raw ACCTID from QFX
    account_type = Column(String)  # CHECKING | SAVINGS | …
    created_at = Column(DateTime, default=datetime.utcnow)

    transactions = relationship("Transaction", back_populates="account")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    color = Column(String, default="#9E9E9E")  # hex used in charts
    is_income = Column(Boolean, default=False)

    rules = relationship(
        "CategorizationRule", back_populates="category", cascade="all, delete-orphan"
    )
    transactions = relationship("Transaction", back_populates="category")


class CategorizationRule(Base):
    __tablename__ = "categorization_rules"

    id = Column(Integer, primary_key=True)
    pattern = Column(String, nullable=False)  # case-insensitive substring
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    priority = Column(Integer, default=0)  # higher wins on tie

    category = relationship("Category", back_populates="rules")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    fitid = Column(String, nullable=False)
    bank = Column(String, nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"))
    date = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(String, nullable=False)
    memo = Column(String)
    category_id = Column(Integer, ForeignKey("categories.id"))
    is_manual_category = Column(Boolean, default=False)
    dedup_hash = Column(String)  # fallback: hash(date|amount|desc)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account", back_populates="transactions")
    category = relationship("Category", back_populates="transactions")

    __table_args__ = (UniqueConstraint("fitid", "bank", name="uq_fitid_bank"),)


class BalanceEntry(Base):
    __tablename__ = "balance_entries"

    id = Column(Integer, primary_key=True)
    label = Column(String, nullable=False)  # e.g. "Scotia Checking"
    account_type = Column(String, nullable=False)  # CHECKING | CREDITCARD | SAVINGS
    balance = Column(Float, nullable=False)
    as_of_date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Goal(Base):
    __tablename__ = "goals"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)  # e.g. "Pay off credit card"
    starting_amount = Column(Float, nullable=False)
    target_amount = Column(Float, nullable=False)
    target_months = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
