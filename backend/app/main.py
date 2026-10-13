from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app.bridge_routes import router as bridge_router
from app.db import create_db_and_tables, engine
from app.deq_device import link_keeper
from app.device_routes import router as device_router
from app.routes import router
from app.seed import seed_factory_profiles

DIST_DIR = Path(__file__).resolve().parents[2] / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    create_db_and_tables()
    with Session(engine) as session:
        seed_factory_profiles(session)
    # The app connects to the unit by itself and keeps trying. Nothing in
    # the frontend asks for a connection: the link is a fact to report.
    link_keeper.start()
    try:
        yield
    finally:
        link_keeper.stop()


app = FastAPI(title="DEQ Tune", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(device_router, prefix="/api")
app.include_router(bridge_router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def register_frontend_routes(app: FastAPI, dist_dir: Path) -> None:
    """Serves the built frontend from `dist_dir`, once it exists. The Docker
    image builds it there. Local dev serves the frontend from Vite instead, so
    `dist_dir` does not exist then, and that is normal."""
    if not dist_dir.exists():
        return

    app.mount("/assets", StaticFiles(directory=dist_dir / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def single_page_app(full_path: str) -> FileResponse:
        candidate = (dist_dir / full_path).resolve()
        if candidate.is_relative_to(dist_dir.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist_dir / "index.html")


register_frontend_routes(app, DIST_DIR)
