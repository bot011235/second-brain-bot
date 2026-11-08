from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings

DEFAULT_URL = "https://second-brain-bot-4wcq.onrender.com"


def ping_once() -> bool:
    base = (settings.public_base_url or DEFAULT_URL).strip().rstrip("/")
    url = f"{base}/healthz"
    try:
        with httpx.Client(timeout=25.0) as client:
            resp = client.get(url, headers={"User-Agent": "SecondBrainKeepAlive/1.0"})
            return resp.status_code == 200
    except Exception:
        return False


def run_loop(interval_sec: int = 240) -> None:
    while True:
        ping_once()
        time.sleep(interval_sec)


if __name__ == "__main__":
    if "--once" in sys.argv:
        ok = ping_once()
        sys.exit(0 if ok else 1)
    run_loop()
