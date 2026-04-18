from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import SessionLocal, engine
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
)
from app.seed import seed

app = FastAPI(title="Budget Maker")

# Create tables on startup
Base.metadata.create_all(bind=engine)

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
