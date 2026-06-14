# File: search.py
"""可組合、可備援的搜尋後端。

設計目標：
- 多家 provider 串成 fallback 鏈：Brave -> Google CSE -> SearXNG -> ddgs。
- 每家內部一個金鑰池，round-robin 輪替；某把吃到 429 / 額度滿就冷卻跳過。
- 任何一家失敗都不會讓整體掛掉，只會掉到下一家。
- 沒有任何金鑰也能跑（自動只用免金鑰的 SearXNG / ddgs）。

對外只暴露 `search_web(query, max_results, timelimit) -> List[SearchHit]`，
讓 app.py 不必管底層用哪家。
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import httpx

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

# 某把金鑰 / 某個 instance 出錯後冷卻的秒數，避免一直撞同一個壞的。
COOLDOWN_SECONDS = 120.0


@dataclass
class SearchHit:
    title: str
    href: str
    body: str = ""
    provider: str = ""


def _split_env(name: str) -> List[str]:
    raw = os.getenv(name, "") or ""
    parts = [p.strip() for p in raw.replace("\n", ",").split(",")]
    return [p for p in parts if p]


def _timelimit_to_days(timelimit: str) -> Optional[int]:
    return {"d": 1, "w": 7, "m": 31, "y": 366}.get(timelimit)


class KeyPool:
    """一池字串（金鑰或 instance URL），round-robin + 失敗冷卻。"""

    def __init__(self, values: List[str]):
        self._values = list(values)
        self._index = 0
        self._cooldown_until: Dict[str, float] = {}
        self._lock = threading.Lock()

    def __bool__(self) -> bool:
        return bool(self._values)

    def available(self) -> List[str]:
        now = time.time()
        return [v for v in self._values if self._cooldown_until.get(v, 0) <= now]

    def next(self) -> Optional[str]:
        with self._lock:
            usable = self.available()
            if not usable:
                return None
            value = usable[self._index % len(usable)]
            self._index += 1
            return value

    def penalize(self, value: str, seconds: float = COOLDOWN_SECONDS) -> None:
        with self._lock:
            self._cooldown_until[value] = time.time() + seconds


@dataclass
class Provider:
    name: str
    pool: KeyPool
    fetch: Callable[[str, str, int, str], List[SearchHit]]
    # fetch(credential, query, max_results, timelimit) -> hits
    needs_credential: bool = True
    extra: Dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# 各家 provider 的實際抓取邏輯
# --------------------------------------------------------------------------- #


def _brave_fetch(api_key: str, query: str, max_results: int, timelimit: str) -> List[SearchHit]:
    params = {
        "q": query,
        "count": str(min(max_results, 20)),
        "country": "tw",
        "search_lang": "zh-hant",
        "spellcheck": "0",
    }
    freshness = {"d": "pd", "w": "pw", "m": "pm", "y": "py"}.get(timelimit)
    if freshness:
        params["freshness"] = freshness

    headers = dict(DEFAULT_HEADERS)
    headers["Accept"] = "application/json"
    headers["X-Subscription-Token"] = api_key

    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        resp = client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params=params,
            headers=headers,
        )

    if resp.status_code in (401, 403):
        raise PermissionError(f"brave key rejected: {resp.status_code}")
    if resp.status_code == 429:
        raise RuntimeError("brave rate limited (429)")
    resp.raise_for_status()

    data = resp.json()
    results = (data.get("web") or {}).get("results") or []
    hits: List[SearchHit] = []
    for r in results[:max_results]:
        href = r.get("url")
        if not href:
            continue
        hits.append(
            SearchHit(
                title=r.get("title") or "",
                href=href,
                body=r.get("description") or "",
                provider="brave",
            )
        )
    return hits


def _google_cse_fetch(api_key: str, query: str, max_results: int, timelimit: str) -> List[SearchHit]:
    cx = os.getenv("GOOGLE_CSE_CX", "").strip()
    if not cx:
        raise PermissionError("GOOGLE_CSE_CX 未設定")

    params = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "num": str(min(max_results, 10)),
        "hl": "zh-TW",
        "gl": "tw",
    }
    days = _timelimit_to_days(timelimit)
    if days:
        params["dateRestrict"] = f"d{days}"

    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        resp = client.get(
            "https://www.googleapis.com/customsearch/v1",
            params=params,
            headers={"Accept": "application/json"},
        )

    if resp.status_code == 429 or (
        resp.status_code == 403 and "rateLimitExceeded" in resp.text
    ):
        raise RuntimeError("google cse quota / rate limited")
    if resp.status_code in (400, 401, 403):
        raise PermissionError(f"google cse rejected: {resp.status_code}")
    resp.raise_for_status()

    data = resp.json()
    items = data.get("items") or []
    hits: List[SearchHit] = []
    for r in items[:max_results]:
        href = r.get("link")
        if not href:
            continue
        hits.append(
            SearchHit(
                title=r.get("title") or "",
                href=href,
                body=r.get("snippet") or "",
                provider="google",
            )
        )
    return hits


def _searxng_fetch(instance: str, query: str, max_results: int, timelimit: str) -> List[SearchHit]:
    base = instance.rstrip("/")
    params = {
        "q": query,
        "format": "json",
        "language": "zh-TW",
        "safesearch": "1",
    }
    if timelimit in ("d", "w", "m", "y"):
        params["time_range"] = {"d": "day", "w": "week", "m": "month", "y": "year"}[
            timelimit
        ]

    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        resp = client.get(f"{base}/search", params=params, headers=DEFAULT_HEADERS)

    if resp.status_code == 429:
        raise RuntimeError("searxng rate limited (429)")
    if resp.status_code in (403, 503):
        raise PermissionError(f"searxng instance unavailable: {resp.status_code}")
    resp.raise_for_status()

    data = resp.json()
    results = data.get("results") or []
    hits: List[SearchHit] = []
    for r in results[:max_results]:
        href = r.get("url")
        if not href:
            continue
        hits.append(
            SearchHit(
                title=r.get("title") or "",
                href=href,
                body=r.get("content") or "",
                provider="searxng",
            )
        )
    return hits


def _import_ddgs():
    try:
        from ddgs import DDGS

        return DDGS
    except ImportError:
        from duckduckgo_search import DDGS

        return DDGS


def _ddgs_fetch(_credential: str, query: str, max_results: int, timelimit: str) -> List[SearchHit]:
    DDGS = _import_ddgs()
    try:
        searcher = DDGS(timeout=20)
    except TypeError:
        searcher = DDGS()

    def _call(**kwargs):
        return list(searcher.text(query, max_results=max_results, **kwargs))

    try:
        try:
            results = _call(region="tw-tzh", safesearch="moderate", timelimit=timelimit)
        except TypeError:
            try:
                results = _call(region="tw-tzh", safesearch="moderate")
            except TypeError:
                results = list(searcher.text(keywords=query, max_results=max_results))
    finally:
        close = getattr(searcher, "close", None)
        if callable(close):
            close()

    hits: List[SearchHit] = []
    for r in results[:max_results]:
        href = r.get("href") or r.get("url")
        if not href:
            continue
        hits.append(
            SearchHit(
                title=r.get("title") or r.get("name") or "",
                href=href,
                body=r.get("body") or r.get("snippet") or "",
                provider="ddgs",
            )
        )
    return hits


# --------------------------------------------------------------------------- #
# Provider 組裝 + fallback 鏈
# --------------------------------------------------------------------------- #

# ddgs 用 "_" 當 placeholder 憑證，代表「不需金鑰、永遠有一把可用」。
_DDGS_POOL = KeyPool(["_"])


def build_providers() -> List[Provider]:
    registry: Dict[str, Provider] = {
        "brave": Provider("brave", KeyPool(_split_env("BRAVE_API_KEYS")), _brave_fetch),
        "google": Provider(
            "google", KeyPool(_split_env("GOOGLE_CSE_KEYS")), _google_cse_fetch
        ),
        "searxng": Provider(
            "searxng",
            KeyPool(_split_env("SEARXNG_INSTANCES")),
            _searxng_fetch,
            needs_credential=True,
        ),
        "ddgs": Provider("ddgs", _DDGS_POOL, _ddgs_fetch, needs_credential=False),
    }

    order_env = _split_env("SEARCH_PROVIDER_ORDER")
    order = order_env or ["brave", "google", "searxng", "ddgs"]

    providers: List[Provider] = []
    for name in order:
        provider = registry.get(name)
        if not provider:
            continue
        # 需金鑰但池子空 -> 跳過（沒設定就當沒這家）。
        if provider.needs_credential and not provider.pool:
            continue
        providers.append(provider)

    return providers


def provider_status() -> List[str]:
    """給 UI 顯示「哪些後端可用、各有幾把金鑰」。"""
    lines = []
    for p in build_providers():
        count = len(p.pool.available()) if p.needs_credential else "免金鑰"
        lines.append(f"{p.name}：{count}")
    return lines


def _run_provider(
    provider: Provider, query: str, max_results: int, timelimit: str, notes: List[str]
) -> List[SearchHit]:
    """在單一 provider 內輪替金鑰，直到成功或所有可用金鑰都失敗。"""
    tried = 0
    pool_size = max(1, len(provider.pool.available()) or 1)

    while tried < pool_size:
        credential = provider.pool.next()
        if credential is None:
            break
        tried += 1

        try:
            hits = provider.fetch(credential, query, max_results, timelimit)
            if hits:
                return hits
            # 空結果不罰金鑰，可能只是這個 query 沒命中。
            return []
        except PermissionError as exc:
            # 金鑰被拒 / 設定錯 -> 長冷卻，換下一把。
            provider.pool.penalize(credential, COOLDOWN_SECONDS * 5)
            notes.append(f"{provider.name} 金鑰失效：{exc}")
        except RuntimeError as exc:
            # 額度 / 限流 -> 一般冷卻，換下一把。
            provider.pool.penalize(credential)
            notes.append(f"{provider.name} 限流：{exc}")
        except Exception as exc:  # noqa: BLE001 - 任何錯都不能炸掉整條鏈
            provider.pool.penalize(credential)
            notes.append(f"{provider.name} 失敗：{type(exc).__name__}")

    return []


def search_web(
    query: str,
    max_results: int = 5,
    timelimit: str = "m",
    notes: Optional[List[str]] = None,
) -> List[SearchHit]:
    """跑 fallback 鏈：第一個有回結果的 provider 就採用。"""
    if notes is None:
        notes = []

    providers = build_providers()
    if not providers:
        notes.append("沒有任何可用的搜尋後端")
        return []

    for provider in providers:
        hits = _run_provider(provider, query, max_results, timelimit, notes)
        if hits:
            return hits

    return []
