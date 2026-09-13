from __future__ import annotations
import logging
from pathlib import Path

import httpx

from .. import media as _media

log = logging.getLogger("video.screenshot")

_ENDPOINT = "https://www.googleapis.com/customsearch/v1"


class ScreenshotError(Exception):
    pass


def search_top_url(query: str, *, api_key: str, cx: str, timeout: int = 10) -> str:
    try:
        r = httpx.get(_ENDPOINT, params={"key": api_key, "cx": cx, "q": query}, timeout=timeout)
    except httpx.HTTPError as e:
        raise ScreenshotError(f"search request failed: {e}") from e
    if r.status_code != 200:
        raise ScreenshotError(f"search HTTP {r.status_code}: {r.text[:200]}")
    items = (r.json() or {}).get("items") or []
    if not items:
        raise ScreenshotError(f"no results for query: {query!r}")
    return items[0]["link"]


def search_and_capture(query: str, out_path: Path, *, api_key: str, cx: str) -> str:
    url = search_top_url(query, api_key=api_key, cx=cx)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _media.capture_screenshot(url, out_path)
    except Exception as e:  # noqa: BLE001 - any capture failure must degrade, never crash the render
        raise ScreenshotError(f"capture failed for {url}: {e}") from e
    return url
