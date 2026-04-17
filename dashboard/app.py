"""
dashboard/app.py — Optional FastAPI web dashboard.

Provides:
  • GET  /               → HTML control panel
  • GET  /api/stats      → JSON bot statistics
  • GET  /api/queue/{chat_id}  → JSON queue for a chat
  • POST /api/skip/{chat_id}   → skip current track
  • POST /api/stop/{chat_id}   → stop playback
  • POST /api/volume/{chat_id} → set volume  body: {"volume": 80}

Protected by a simple Bearer token (DASHBOARD_SECRET from .env).

Start it as:
    asyncio.create_task(start_dashboard())
"""

import asyncio
import os
from typing import Any, Dict

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from bot.config import config
from bot.database import get_stats, get_now_playing, queue_get_all, get_volume
from bot.player.music_player import music_player
from bot.utils.logger import get_logger

log = get_logger(__name__)

app = FastAPI(
    title=f"{config.BOT_NAME} Dashboard",
    version="1.0.0",
    docs_url="/docs" if os.getenv("DEBUG") else None,   # disable swagger in prod
    redoc_url=None,
)

_templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=_templates_dir)

_bearer = HTTPBearer(auto_error=False)


# ── Auth ──────────────────────────────────────────────────────────────────────

def _check_auth(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> None:
    """Validate Bearer token against DASHBOARD_SECRET."""
    token = credentials.credentials if credentials else None
    if token != config.DASHBOARD_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── HTML dashboard ────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    """Serve the main HTML control panel."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "bot_name": config.BOT_NAME,
        },
    )


# ── REST API ──────────────────────────────────────────────────────────────────

@app.get("/api/stats", dependencies=[Depends(_check_auth)])
async def api_stats() -> Dict[str, Any]:
    """Return global bot and database statistics."""
    from bot.utils.cache_manager import get_cache_stats
    from bot.utils.decorators import get_uptime

    db_stats = await get_stats()
    cache = await get_cache_stats()

    return {
        "bot_name": config.BOT_NAME,
        "uptime": get_uptime(),
        "database": db_stats,
        "cache": cache,
    }


@app.get("/api/queue/{chat_id}", dependencies=[Depends(_check_auth)])
async def api_queue(chat_id: int) -> Dict[str, Any]:
    """Return the current queue for a given chat_id."""
    tracks = await queue_get_all(chat_id)
    np = await get_now_playing(chat_id)
    volume = await get_volume(chat_id)

    return {
        "chat_id": chat_id,
        "now_playing": np,
        "volume": volume,
        "queue_length": len(tracks),
        "queue": tracks,
    }


@app.post("/api/skip/{chat_id}", dependencies=[Depends(_check_auth)])
async def api_skip(chat_id: int) -> Dict[str, str]:
    """Skip the current track in the specified chat."""
    if not music_player.is_active(chat_id):
        raise HTTPException(status_code=404, detail="No active stream in this chat.")
    await music_player.skip(chat_id)
    return {"status": "skipped"}


@app.post("/api/stop/{chat_id}", dependencies=[Depends(_check_auth)])
async def api_stop(chat_id: int) -> Dict[str, str]:
    """Stop playback and clear the queue for the specified chat."""
    await music_player.stop(chat_id)
    return {"status": "stopped"}


class VolumePayload(BaseModel):
    volume: int  # 1–200


@app.post("/api/volume/{chat_id}", dependencies=[Depends(_check_auth)])
async def api_set_volume(chat_id: int, payload: VolumePayload) -> Dict[str, Any]:
    """Set playback volume for the specified chat."""
    if not 1 <= payload.volume <= 200:
        raise HTTPException(status_code=400, detail="Volume must be between 1 and 200.")
    await music_player.set_volume(chat_id, payload.volume)
    return {"status": "ok", "volume": payload.volume}


@app.post("/api/pause/{chat_id}", dependencies=[Depends(_check_auth)])
async def api_pause(chat_id: int) -> Dict[str, str]:
    """Pause playback for the specified chat."""
    success = await music_player.pause(chat_id)
    if not success:
        raise HTTPException(status_code=409, detail="Stream is not playing or already paused.")
    return {"status": "paused"}


@app.post("/api/resume/{chat_id}", dependencies=[Depends(_check_auth)])
async def api_resume(chat_id: int) -> Dict[str, str]:
    """Resume playback for the specified chat."""
    success = await music_player.resume(chat_id)
    if not success:
        raise HTTPException(status_code=409, detail="Stream is not paused.")
    return {"status": "resumed"}


# ── Startup / shutdown hooks ──────────────────────────────────────────────────

@app.on_event("startup")
async def on_startup():
    log.info(f"Dashboard API started on port {config.DASHBOARD_PORT}")


@app.on_event("shutdown")
async def on_shutdown():
    log.info("Dashboard API shutting down")


# ── Runner ────────────────────────────────────────────────────────────────────

async def start_dashboard() -> None:
    """Launch uvicorn in a background asyncio task."""
    server_config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=config.DASHBOARD_PORT,
        log_level="warning",   # keep dashboard logs quiet
        loop="none",           # use the existing event loop
    )
    server = uvicorn.Server(server_config)
    await server.serve()
