"""
Auto-categorization engine.
Loads all rules from DB and matches against a transaction description.
Higher priority wins; on equal priority, first match wins.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import CategorizationRule, Category


def categorize(description: str, db: Session) -> int | None:
    """
    Return the category_id that best matches description, or None.
    Rules are matched case-insensitively as substrings.
    """
    desc_lower = description.lower()

    rules: list[CategorizationRule] = (
        db.query(CategorizationRule).order_by(CategorizationRule.priority.desc()).all()
    )

    for rule in rules:
        if rule.pattern.lower() in desc_lower:
            return rule.category_id

    # Fall back to "Other" category
    other = db.query(Category).filter(Category.name == "Other").first()
    return other.id if other else None
