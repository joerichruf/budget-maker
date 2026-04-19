from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from app.database import SessionLocal, engine, ensure_db_dir
from app.models import Base
from app.routers import (
    budgets,
    digest,
    goals,
    imports,
    insights,
    review,
    subscriptions,
    transactions,
    users,
)
from app.seed import seed

app = FastAPI(title="Budget Maker")

# Ensure DB directory exists (matters when /data is a mounted volume)
ensure_db_dir()

# Create tables on startup (new tables only; existing tables are not dropped)
Base.metadata.create_all(bind=engine)

# Add new columns to existing tables when they are missing (no Alembic)
with engine.connect() as conn:
    existing_cols = {col["name"] for col in inspect(engine).get_columns("accounts")}
    if "user_id" not in existing_cols:
        conn.execute(
            text("ALTER TABLE accounts ADD COLUMN user_id INTEGER REFERENCES users(id)")
        )
        conn.commit()

# Seed default categories and rules once
with SessionLocal() as db:
    seed(db)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(imports.router)
app.include_router(transactions.router)
app.include_router(insights.router)
app.include_router(goals.router)
app.include_router(review.router)
app.include_router(budgets.router)
app.include_router(subscriptions.router)
app.include_router(digest.router)
app.include_router(users.router)
