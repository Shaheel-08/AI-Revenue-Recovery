"""RecoverOS — AI Revenue Recovery Agent — FastAPI Application."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db.session import init_db, close_db


def _auto_train_ml():
    """Auto-train ML model on startup if no model file exists."""
    from app.ml.recovery_predictor import recovery_predictor
    settings = get_settings()
    model_path = os.path.join(settings.data_dir, "recovery_model.joblib")
    csv_path = os.path.join(settings.data_dir, "synthetic_transactions.csv")

    if os.path.exists(model_path):
        loaded = recovery_predictor.load(settings.data_dir)
        if loaded:
            return
    if os.path.exists(csv_path):
        print("\n🧠 Auto-training recovery predictor from synthetic data...")
        try:
            recovery_predictor.train(csv_path, settings.data_dir)
            print("✅ ML model trained and saved.\n")
        except Exception as e:
            print(f"⚠ ML training failed (using heuristic fallback): {e}\n")
    else:
        print("⚠ No synthetic data found — ML model using heuristic fallback.\n")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB on startup, train ML, cleanup on shutdown."""
    await init_db()
    _auto_train_ml()
    yield
    await close_db()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="RecoverOS",
        description=(
            "AI Revenue Recovery Agent — diagnoses payment failures, "
            "simulates recovery actions, executes the highest-value intervention, "
            "and learns from outcomes."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS — allow frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url, "http://localhost:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Mount routers (lazy import to avoid circular deps) ──
    from app.api.webhooks import router as webhooks_router
    from app.api.dashboard import router as dashboard_router
    from app.api.recovery import router as recovery_router
    from app.api.approvals import router as approvals_router
    from app.api.policy import router as policy_router
    from app.api.payments import router as payments_router
    from app.api.customers import router as customers_router
    from app.api.demo import router as demo_router

    app.include_router(webhooks_router, prefix="/webhooks", tags=["Webhooks"])
    app.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
    app.include_router(recovery_router, prefix="/transactions", tags=["Recovery"])
    app.include_router(approvals_router, prefix="/approvals", tags=["Approvals"])
    app.include_router(policy_router, prefix="/policy", tags=["Policy"])
    app.include_router(payments_router, prefix="/simulate", tags=["Simulation"])
    app.include_router(customers_router, prefix="/customers", tags=["Customers"])
    app.include_router(demo_router, prefix="/demo", tags=["Demo"])

    @app.get("/", tags=["Health"])
    async def root():
        return {
            "name": "RecoverOS",
            "version": "1.0.0",
            "status": "operational",
            "description": "AI Revenue Recovery Agent",
        }

    @app.get("/health", tags=["Health"])
    async def health():
        return {"status": "healthy"}

    return app


app = create_app()
