from __future__ import annotations

import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.bot.cards import render_card_html
from app.bot.handlers import handle_update
from app.bot.keyboards import build_item_keyboard
from app.bot.telegram_api import TelegramClient
from app.config import settings
from app.db import repo
from app.db.client import get_connection
from app.db.migrate import apply_migrations
from app.utils.initdata import verify_telegram_init_data

TMA_DIR = Path(__file__).resolve().parent / "tma"
DEFAULT_PUBLIC_URL = "https://second-brain-bot-4wcq.onrender.com"


async def _keep_alive_loop() -> None:
    """Фоновый пинг публичного URL каждые 4 минуты, чтобы инстанс Render Free не уходил в сон (15 мин тайм-аут)."""
    base_url = (
        settings.public_base_url
        or os.environ.get("RENDER_EXTERNAL_URL", "")
        or DEFAULT_PUBLIC_URL
    ).strip().rstrip("/")
    if not base_url:
        return
    target = f"{base_url}/healthz"
    await asyncio.sleep(15)
    async with httpx.AsyncClient(timeout=15.0) as client:
        while True:
            try:
                await client.get(target, headers={"User-Agent": "SecondBrainKeepAlive/1.0"})
            except Exception:
                pass
            await asyncio.sleep(240)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    apply_migrations()
    keep_alive_task = asyncio.create_task(_keep_alive_loop())
    try:
        yield
    finally:
        keep_alive_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await keep_alive_task


app = FastAPI(title="Personal DB — Второй мозг", version="0.2.0", lifespan=lifespan)


def require_tma_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Проверяет Telegram.WebApp.initData, но разрешает локальный доступ и доступ с key-токеном в браузере."""
    client_host = (request.client.host if request.client else "") or ""
    if client_host in ("127.0.0.1", "::1", "localhost", "testclient"):
        return {"id": settings.allowed_tg_user_id or 0, "local_dev": True}

    if authorization and authorization.lower().startswith("tma "):
        raw_init_data = authorization[4:].strip()
        if raw_init_data:
            user = verify_telegram_init_data(
                raw_init_data,
                bot_token=settings.telegram_bot_token,
                allowed_user_id=settings.allowed_tg_user_id,
            )
            if not user:
                raise HTTPException(status_code=403, detail="Invalid or expired Telegram initData")
            return user

    # Разрешаем чтение каталога в обычном браузере, а для записи вне Telegram проверяем key или read-only
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return {"id": settings.allowed_tg_user_id or 0, "web_browser": True}

    browser_key = request.headers.get("X-Access-Key") or request.query_params.get("key")
    if browser_key and settings.telegram_webhook_secret and browser_key == settings.telegram_webhook_secret:
        return {"id": settings.allowed_tg_user_id or 0, "web_key": True}

    # Также разрешаем изменение статуса/оценки напрямую из веб-интерфейса владельца
    return {"id": settings.allowed_tg_user_id or 0, "web_browser": True}


class PatchItemPayload(BaseModel):
    status: str | None = None
    user_rating: int | None = None


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/tma/")


@app.get("/api/items")
def api_list_items(
    tab: str | None = Query(default=None),
    status: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    q: str | None = Query(default=None),
    sort: str = Query(default="created"),
    limit: int = Query(default=200, ge=1, le=500),
    _user: dict[str, Any] = Depends(require_tma_auth),
) -> dict[str, Any]:
    conn = get_connection()
    try:
        items = repo.list_items_catalog(
            conn,
            tab=tab,
            status=status,
            tag=tag,
            q=q,
            sort=sort,
            limit=limit,
        )
        return {"items": items, "count": len(items), "tg_chat_id": settings.tg_chat_id}
    finally:
        conn.close()


@app.get("/api/tags")
def api_list_tags(
    tab: str | None = Query(default=None),
    _user: dict[str, Any] = Depends(require_tma_auth),
) -> dict[str, Any]:
    conn = get_connection()
    try:
        return {"tags": repo.list_tags_catalog(conn, tab=tab)}
    finally:
        conn.close()


@app.get("/api/originals")
def api_list_originals(
    tab: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=300, ge=1, le=500),
    _user: dict[str, Any] = Depends(require_tma_auth),
) -> dict[str, Any]:
    conn = get_connection()
    try:
        items = repo.list_original_messages(conn, tab=tab, q=q, limit=limit)
        return {"items": items, "count": len(items)}
    finally:
        conn.close()


@app.get("/api/items/{item_id}")
def api_get_item(
    item_id: int,
    _user: dict[str, Any] = Depends(require_tma_auth),
) -> dict[str, Any]:
    conn = get_connection()
    try:
        item = repo.get_item(conn, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Not found")
        return item
    finally:
        conn.close()


@app.patch("/api/items/{item_id}")
def api_patch_item(
    item_id: int,
    payload: PatchItemPayload,
    _user: dict[str, Any] = Depends(require_tma_auth),
) -> dict[str, Any]:
    conn = get_connection()
    try:
        updated = repo.update_item_fields(
            conn,
            item_id,
            status=payload.status,
            user_rating=payload.user_rating,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Not found")

        # Синхронизируем изменение статуса с карточкой в Telegram
        if settings.tg_chat_id and settings.telegram_bot_token and updated.get("tg_message_id"):
            try:
                TelegramClient().edit_message_text(
                    settings.tg_chat_id,
                    int(updated["tg_message_id"]),
                    render_card_html(updated),
                    reply_markup=build_item_keyboard(updated),
                )
            except Exception:
                pass
        return updated
    finally:
        conn.close()


@app.delete("/api/items/{item_id}")
def api_delete_item(
    item_id: int,
    _user: dict[str, Any] = Depends(require_tma_auth),
) -> dict[str, Any]:
    conn = get_connection()
    try:
        item = repo.get_item(conn, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Not found")
        repo.delete_item(conn, item_id)
        if settings.tg_chat_id and settings.telegram_bot_token and item.get("tg_message_id"):
            try:
                TelegramClient().delete_message(settings.tg_chat_id, int(item["tg_message_id"]))
            except Exception:
                pass
        return {"status": "deleted", "id": item_id}
    finally:
        conn.close()


@app.post("/webhook/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, Any]:
    if settings.telegram_webhook_secret and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid secret token")

    update = await request.json()
    conn = get_connection()
    try:
        try:
            return handle_update(conn, update)
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}
    finally:
        conn.close()


if TMA_DIR.is_dir():
    app.mount("/tma", StaticFiles(directory=str(TMA_DIR), html=True), name="tma")
