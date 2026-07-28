from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .auth import require_admin
from .config import get_settings
from .database import Base, SessionLocal, engine, get_db
from .models import User
from .routers import auth, calibration, holidays, preopen, reports, settings as settings_router
from .schemas import MessageOut
from .services.scheduler import resync_schedule, start_scheduler, stop_scheduler
from .services.seed import ensure_admin_user, seed_holidays, seed_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _migrate_sqlite()
    db = SessionLocal()
    try:
        ensure_admin_user(db)
        seed_settings(db)
        seed_holidays(db, only_missing=True)
    finally:
        db.close()
    start_scheduler()
    yield
    stop_scheduler()


def _migrate_sqlite() -> None:
    """Add newer columns to existing SQLite DBs."""
    settings = get_settings()
    if not settings.database_url.startswith("sqlite"):
        return
    from sqlalchemy import text

    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(reports)")).fetchall()}
        if "progress_pct" not in cols:
            conn.execute(text("ALTER TABLE reports ADD COLUMN progress_pct INTEGER DEFAULT 0"))
        if "progress_message" not in cols:
            conn.execute(text("ALTER TABLE reports ADD COLUMN progress_message VARCHAR(255) DEFAULT ''"))


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(holidays.router)
    app.include_router(reports.router)
    app.include_router(settings_router.router)
    app.include_router(calibration.router)
    app.include_router(preopen.router)

    @app.get("/api/health")
    def health():
        from premarket.analyze import llm_status

        return {"ok": True, "app": settings.app_name, "llm": llm_status()}

    @app.post("/api/admin/resync-schedule", response_model=MessageOut)
    def admin_resync(user: User = Depends(require_admin), db: Session = Depends(get_db)):
        cron = resync_schedule()
        return MessageOut(message=f"Schedule set to '{cron}' IST")

    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.exists():
        assets = dist / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}")
        def spa(full_path: str):
            if full_path.startswith("api/"):
                return {"detail": "Not found"}
            index = dist / "index.html"
            file_path = dist / full_path
            if full_path and file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(index)

    return app


app = create_app()
