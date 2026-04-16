"""
Seeds the database with default categories and categorization rules.
Safe to call multiple times — skips already-existing entries.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import CategorizationRule, Category

CATEGORIES: list[dict] = [
    {"name": "Groceries", "color": "#4CAF50", "is_income": False},
    {"name": "Restaurants & Coffee", "color": "#FF9800", "is_income": False},
    {"name": "Transportation", "color": "#2196F3", "is_income": False},
    {"name": "Utilities", "color": "#9C27B0", "is_income": False},
    {"name": "Entertainment", "color": "#E91E63", "is_income": False},
    {"name": "Shopping", "color": "#00BCD4", "is_income": False},
    {"name": "Health", "color": "#F44336", "is_income": False},
    {"name": "Travel", "color": "#795548", "is_income": False},
    {"name": "Financial", "color": "#607D8B", "is_income": False},
    {"name": "Income", "color": "#8BC34A", "is_income": True},
    {"name": "Other", "color": "#9E9E9E", "is_income": False},
]

# (pattern, category_name, priority)
RULES: list[tuple[str, str, int]] = [
    # Groceries
    ("loblaws", "Groceries", 10),
    ("sobeys", "Groceries", 10),
    ("metro", "Groceries", 10),
    ("freshco", "Groceries", 10),
    ("food basics", "Groceries", 10),
    ("no frills", "Groceries", 10),
    ("superstore", "Groceries", 10),
    ("provigo", "Groceries", 10),
    ("maxi", "Groceries", 10),
    ("farm boy", "Groceries", 10),
    ("t&t", "Groceries", 10),
    ("iga", "Groceries", 10),
    ("walmart", "Groceries", 5),  # lower priority — also used for non-grocery
    ("costco", "Groceries", 5),
    # Restaurants & Coffee
    ("tim horton", "Restaurants & Coffee", 10),
    ("starbucks", "Restaurants & Coffee", 10),
    ("mcdonald", "Restaurants & Coffee", 10),
    ("subway", "Restaurants & Coffee", 10),
    ("burger king", "Restaurants & Coffee", 10),
    ("wendy", "Restaurants & Coffee", 10),
    ("harvey", "Restaurants & Coffee", 10),
    ("a&w", "Restaurants & Coffee", 10),
    ("kfc", "Restaurants & Coffee", 10),
    ("popeyes", "Restaurants & Coffee", 10),
    ("swiss chalet", "Restaurants & Coffee", 10),
    ("boston pizza", "Restaurants & Coffee", 10),
    ("east side mario", "Restaurants & Coffee", 10),
    ("doordash", "Restaurants & Coffee", 10),
    ("uber eats", "Restaurants & Coffee", 10),
    ("skip the dishes", "Restaurants & Coffee", 10),
    ("skipthedishes", "Restaurants & Coffee", 10),
    # Transportation
    ("esso", "Transportation", 10),
    ("shell", "Transportation", 10),
    ("petro-canada", "Transportation", 10),
    ("petro canada", "Transportation", 10),
    ("ultramar", "Transportation", 10),
    ("husky", "Transportation", 10),
    ("sunoco", "Transportation", 10),
    ("presto", "Transportation", 10),
    ("translink", "Transportation", 10),
    ("ttc", "Transportation", 10),
    ("stm ", "Transportation", 10),
    ("oc transpo", "Transportation", 10),
    ("go transit", "Transportation", 10),
    ("via rail", "Transportation", 10),
    ("parking", "Transportation", 8),
    ("impark", "Transportation", 10),
    ("uber", "Transportation", 5),  # lower — uber eats matched first
    ("lyft", "Transportation", 10),
    # Utilities
    ("hydro", "Utilities", 10),
    ("enbridge", "Utilities", 10),
    ("fortis", "Utilities", 10),
    ("rogers", "Utilities", 10),
    ("bell ", "Utilities", 10),
    ("telus", "Utilities", 10),
    ("fido", "Utilities", 10),
    ("koodo", "Utilities", 10),
    ("virgin mobile", "Utilities", 10),
    ("shaw", "Utilities", 10),
    ("videotron", "Utilities", 10),
    ("cogeco", "Utilities", 10),
    # Entertainment
    ("netflix", "Entertainment", 10),
    ("spotify", "Entertainment", 10),
    ("disney", "Entertainment", 10),
    ("crave", "Entertainment", 10),
    ("apple tv", "Entertainment", 10),
    ("amazon prime", "Entertainment", 10),
    ("youtube premium", "Entertainment", 10),
    ("steam", "Entertainment", 10),
    ("xbox", "Entertainment", 10),
    ("playstation", "Entertainment", 10),
    ("nintendo", "Entertainment", 10),
    ("cineplex", "Entertainment", 10),
    ("landmark", "Entertainment", 10),
    ("apple music", "Entertainment", 10),
    # Shopping
    ("amazon", "Shopping", 5),  # lower — amazon prime matched first
    ("canadian tire", "Shopping", 10),
    ("home depot", "Shopping", 10),
    ("ikea", "Shopping", 10),
    ("hudson bay", "Shopping", 10),
    ("the bay", "Shopping", 10),
    ("winners", "Shopping", 10),
    ("marshalls", "Shopping", 10),
    ("homesense", "Shopping", 10),
    ("old navy", "Shopping", 10),
    ("h&m", "Shopping", 10),
    ("zara", "Shopping", 10),
    ("sport chek", "Shopping", 10),
    ("best buy", "Shopping", 10),
    ("staples", "Shopping", 10),
    ("uniqlo", "Shopping", 10),
    # Health
    ("shoppers drug", "Health", 10),
    ("rexall", "Health", 10),
    ("jean coutu", "Health", 10),
    ("lawtons", "Health", 10),
    ("guardian pharm", "Health", 10),
    ("pharmacy", "Health", 8),
    ("medical", "Health", 8),
    ("dentist", "Health", 8),
    ("dental", "Health", 8),
    ("optician", "Health", 8),
    ("massage", "Health", 8),
    ("physio", "Health", 8),
    ("clinic", "Health", 5),
    ("hospital", "Health", 5),
    # Travel
    ("airbnb", "Travel", 10),
    ("air canada", "Travel", 10),
    ("westjet", "Travel", 10),
    ("sunwing", "Travel", 10),
    ("porter", "Travel", 10),
    ("expedia", "Travel", 10),
    ("booking.com", "Travel", 10),
    ("hotels.com", "Travel", 10),
    ("marriott", "Travel", 10),
    ("hilton", "Travel", 10),
    ("hyatt", "Travel", 10),
    ("holiday inn", "Travel", 10),
    # Financial
    ("insurance", "Financial", 8),
    ("manulife", "Financial", 10),
    ("sunlife", "Financial", 10),
    ("great-west", "Financial", 10),
    ("bank fee", "Financial", 10),
    ("service charge", "Financial", 10),
    ("annual fee", "Financial", 10),
    ("interest chg", "Financial", 10),
    ("nsf fee", "Financial", 10),
    ("overdraft", "Financial", 10),
    # Income
    ("payroll", "Income", 10),
    ("direct deposit", "Income", 10),
    ("salary", "Income", 10),
    ("e-transfer rcvd", "Income", 10),
    ("etransfer rcv", "Income", 10),
    ("tax refund", "Income", 10),
    ("cra", "Income", 5),
]


def seed(db: Session) -> None:
    # Insert categories that don't exist yet
    category_map: dict[str, int] = {}
    for cat_data in CATEGORIES:
        cat = db.query(Category).filter_by(name=cat_data["name"]).first()
        if not cat:
            cat = Category(**cat_data)
            db.add(cat)
            db.flush()
        category_map[cat.name] = cat.id

    # Insert rules that don't exist yet (match on pattern + category)
    for pattern, cat_name, priority in RULES:
        cat_id = category_map.get(cat_name)
        if cat_id is None:
            continue
        exists = (
            db.query(CategorizationRule)
            .filter_by(pattern=pattern, category_id=cat_id)
            .first()
        )
        if not exists:
            db.add(
                CategorizationRule(
                    pattern=pattern, category_id=cat_id, priority=priority
                )
            )

    db.commit()
