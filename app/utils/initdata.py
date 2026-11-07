from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl


def verify_telegram_init_data(
    init_data: str,
    bot_token: str,
    allowed_user_id: int = 0,
    max_age_seconds: int = 86400,
) -> dict[str, Any] | None:
    """Проверяет криптографическую подпись HMAC-SHA256 для Telegram.WebApp.initData."""
    if not init_data or not bot_token:
        return None

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    auth_date_raw = pairs.get("auth_date")
    if auth_date_raw and auth_date_raw.isdigit():
        if max_age_seconds > 0 and (time.time() - int(auth_date_raw)) > max_age_seconds:
            return None

    user_raw = pairs.get("user")
    user_obj: dict[str, Any] = {}
    if user_raw:
        try:
            user_obj = json.loads(user_raw)
        except Exception:
            return None

    if allowed_user_id and int(user_obj.get("id", 0)) != int(allowed_user_id):
        return None

    return user_obj
