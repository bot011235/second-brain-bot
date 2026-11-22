from __future__ import annotations

import asyncio
import contextlib
import hmac
import mimetypes
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.bot.cards import render_card_html
from app.bot.handlers import handle_update, ingest_web_item, reenrich_item
from app.bot.keyboards import build_item_keyboard
from app.bot.telegram_api import TelegramClient
from app.config import settings
from app.db import repo
from app.db.client import get_connection
from app.db.migrate import apply_migrations
from app.utils.initdata import verify_telegram_init_data

TMA_DIR = Path(__file__).resolve().parent / "tma"
DEFAULT_PUBLIC_URL = "https://second-brain-bot-4wcq.onrender.com"
mimetypes.add_type("application/manifest+json", ".webmanifest")


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


app = FastAPI(
    title="Personal DB — Notes",
    version="0.2.1",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def require_tma_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Строгая авторизация доступа к API:
    1. TestClient в автоматических тестах.
    2. Telegram Mini App: криптографическая проверка подписи initData и вайтлист user_id.
    3. Веб-браузер владельца: проверка секретного ключа (X-Access-Key, Authorization: Bearer, ?key= или cookie).
    Любые неавторизованные запросы немедленно отклоняются с кодом 401/403.
    """
    client_host = (request.client.host if request.client else "") or ""
    if client_host == "testclient":
        return {"id": settings.allowed_tg_user_id or 0, "local_test": True}

    # Telegram Mini App (HMAC-SHA256 подпись данных Telegram)
    if authorization and authorization.lower().startswith("tma "):
        raw_init_data = authorization[4:].strip()
        if raw_init_data:
            user = verify_telegram_init_data(
                raw_init_data,
                bot_token=settings.telegram_bot_token,
                allowed_user_id=settings.allowed_tg_user_id,
            )
            if not user:
                raise HTTPException(status_code=403, detail="Forbidden: unauthorized or invalid Telegram user")
            return user

    # Веб-доступ владельца через секретный ключ или пароль администратора
    expected_key = (
        settings.web_admin_password
        or settings.web_access_key
        or settings.telegram_webhook_secret
        or ""
    ).strip()
    if expected_key:
        provided_key = (
            request.headers.get("X-Access-Key")
            or request.query_params.get("key")
            or request.cookies.get("sb_access_key")
            or ""
        ).strip()

        if not provided_key and authorization and authorization.lower().startswith("bearer "):
            provided_key = authorization[7:].strip()

        if provided_key and hmac.compare_digest(provided_key, expected_key):
            return {"id": settings.allowed_tg_user_id or 0, "web_key": True}

    raise HTTPException(
        status_code=401,
        detail="Unauthorized: Telegram Mini App authentication or valid access key required",
    )


class LoginPayload(BaseModel):
    username: str
    password: str


class PatchItemPayload(BaseModel):
    status: str | None = None
    user_rating: int | None = None
    title_ru: str | None = None
    summary: str | None = None
    user_note: str | None = None
    tags: list[str] | None = None
    highlights: list[dict[str, Any]] | None = None
    progress: dict[str, Any] | None = None


class CreateItemPayload(BaseModel):
    text: str
    topic: str = "auto"
    skip_original: bool = False
    record_original_only: bool = False


class BulkItemsPayload(BaseModel):
    item_ids: list[int]
    status: str | None = None
    add_tag: str | None = None
    delete: bool = False


@app.post("/api/login")
def api_login(
    payload: LoginPayload,
    response: Response,
) -> dict[str, Any]:
    """Проверка логина и пароля с установкой cookie для браузерных менеджеров паролей (Google Passwords, Apple Keychain)."""
    expected_username = (settings.web_admin_username or "admin").strip().lower()
    input_username = payload.username.strip().lower()
    if input_username != expected_username:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    expected_password = (
        settings.web_admin_password
        or settings.web_access_key
        or settings.telegram_webhook_secret
        or ""
    ).strip()
    if not expected_password:
        raise HTTPException(status_code=500, detail="Server auth not configured")

    input_password = payload.password.strip()
    if not hmac.compare_digest(input_password, expected_password):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    # Успешная аутентификация: выставляем cookie sb_access_key на 1 год
    response.set_cookie(
        key="sb_access_key",
        value=input_password,
        max_age=365 * 24 * 3600,
        httponly=False,
        samesite="lax",
        secure=True,
    )
    return {
        "status": "ok",
        "username": payload.username.strip(),
        "token": input_password,
    }


@app.post("/api/logout")
def api_logout(response: Response) -> dict[str, str]:
    response.delete_cookie(key="sb_access_key", path="/")
    return {"status": "logged_out"}


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
    offset: int = Query(default=0, ge=0),
    smart: str | None = Query(default=None),
    _user: dict[str, Any] = Depends(require_tma_auth),
) -> dict[str, Any]:
    conn = get_connection()
    safe_offset = offset if isinstance(offset, int) else 0
    try:
        items = repo.list_items_catalog(
            conn,
            tab=tab,
            status=status,
            tag=tag,
            q=q,
            sort=sort,
            limit=limit,
            offset=safe_offset,
            smart=smart,
        )
        status_counts: dict[str, int] | None = None
        if safe_offset == 0 and (not status or status == "all") and not tag and not q and not smart:
            status_counts = repo.get_status_counts_by_tab(conn, tab=tab)
            total = status_counts["all"]
        else:
            total = repo.count_items_catalog(conn, tab=tab, status=status, tag=tag, q=q, smart=smart)
        res: dict[str, Any] = {
            "items": items,
            "count": len(items),
            "total": total,
            "has_more": (safe_offset + len(items)) < total,
            "tg_chat_id": settings.tg_chat_id,
        }
        if status_counts is not None:
            res["status_counts"] = status_counts
        return res
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


@app.get("/api/stats")
def api_get_stats(
    year: int | None = Query(default=None, ge=2000, le=2100),
    _user: dict[str, Any] = Depends(require_tma_auth),
) -> dict[str, Any]:
    conn = get_connection()
    try:
        return repo.get_catalog_stats(conn, year=year)
    finally:
        conn.close()


@app.post("/api/items/bulk")
def api_bulk_items(
    payload: BulkItemsPayload,
    _user: dict[str, Any] = Depends(require_tma_auth),
) -> dict[str, Any]:
    conn = get_connection()
    try:
        try:
            return repo.bulk_update_items(
                conn,
                payload.item_ids,
                status=payload.status,
                add_tag=payload.add_tag,
                delete=payload.delete,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
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
        return {"items": items, "count": len(items), "tg_chat_id": settings.tg_chat_id}
    finally:
        conn.close()


@app.delete("/api/originals/{orig_id}")
def api_delete_original(
    orig_id: int,
    _user: dict[str, Any] = Depends(require_tma_auth),
) -> dict[str, Any]:
    conn = get_connection()
    try:
        res = repo.delete_original_message(conn, orig_id)
        if not res:
            raise HTTPException(status_code=404, detail="Not found")
        deleted_items = res.get("deleted_items") or []
        return {
            "status": "deleted",
            "id": orig_id,
            "deleted_item_ids": [it["id"] for it in deleted_items],
        }
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


@app.post("/api/items")
def api_create_item(
    payload: CreateItemPayload,
    _user: dict[str, Any] = Depends(require_tma_auth),
) -> dict[str, Any]:
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")
    conn = get_connection()
    try:
        res = ingest_web_item(
            conn,
            text,
            topic=payload.topic,
            skip_original=payload.skip_original,
            record_original_only=payload.record_original_only,
        )
        if res.get("item_id"):
            item = repo.get_item(conn, int(res["item_id"]))
            if item:
                res["item"] = item
        return res
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
        try:
            updated = repo.update_item_fields(
                conn,
                item_id,
                status=payload.status,
                user_rating=payload.user_rating,
                title_ru=payload.title_ru,
                summary=payload.summary,
                user_note=payload.user_note,
                tags=payload.tags,
                highlights=payload.highlights,
                progress=payload.progress,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not updated:
            raise HTTPException(status_code=404, detail="Not found")
        return updated
    finally:
        conn.close()


@app.post("/api/items/{item_id}/reenrich")
def api_reenrich_item(
    item_id: int,
    _user: dict[str, Any] = Depends(require_tma_auth),
) -> dict[str, Any]:
    conn = get_connection()
    try:
        res = reenrich_item(conn, item_id)
        if res.get("status") == "not_found":
            raise HTTPException(status_code=404, detail="Not found")
        return res
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
        return {"status": "deleted", "id": item_id}
    finally:
        conn.close()


def _process_telegram_update_bg(update_payload: dict[str, Any]) -> None:
    """Обрабатывает Telegram-апдейт в фоне без блокировки HTTP-ответа webhook."""
    conn = get_connection()
    try:
        try:
            handle_update(conn, update_payload)
        except Exception:
            pass
    finally:
        conn.close()


@app.post("/webhook/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    background_tasks: BackgroundTasks = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    secret = (settings.telegram_webhook_secret or "").strip()
    token = (x_telegram_bot_api_secret_token or "").strip()
    if not secret or not hmac.compare_digest(token, secret):
        raise HTTPException(status_code=403, detail="Invalid secret token")

    update = await request.json()
    if background_tasks is not None:
        background_tasks.add_task(_process_telegram_update_bg, update)
    else:
        _process_telegram_update_bg(update)
    return {"status": "accepted"}


if TMA_DIR.is_dir():
    app.mount("/tma", StaticFiles(directory=str(TMA_DIR), html=True), name="tma")
