"""GitHub API helpers with rate-limit awareness and local issue/PR cache."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import requests

GITHUB_API = "https://api.github.com"
ESPHOME_REPO = "esphome/esphome"

_COMPONENT_PREFIX = "component: "
_EMPTY_COUNTS = {"open_issues": 0, "open_prs": 0}


def _session() -> requests.Session:
    s = requests.Session()
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    s.headers["Accept"] = "application/vnd.github+json"
    s.headers["X-GitHub-Api-Version"] = "2022-11-28"
    s.headers["User-Agent"] = "esphome-kpis/0.1 (https://github.com/rwrozelle/esphome-kpis)"
    return s


_SESSION = _session()


def get(path: str, **params) -> dict | list:
    url = f"{GITHUB_API}/{path.lstrip('/')}"
    while True:
        r = _SESSION.get(url, params=params)
        if r.status_code == 403 and "rate limit" in r.text.lower():
            reset = int(r.headers.get("X-RateLimit-Reset", time.time() + 60))
            wait = max(reset - time.time(), 1)
            print(f"Rate limited — sleeping {wait:.0f}s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()


def paginate(path: str, **params) -> list:
    params.setdefault("per_page", 100)
    results = []
    page = 1
    while True:
        data = get(path, page=page, **params)
        if not data:
            break
        results.extend(data)
        if len(data) < params["per_page"]:
            break
        page += 1
    return results


def releases() -> list[dict]:
    """Return all stable releases sorted oldest-first, with tag and date."""
    data = paginate(f"repos/{ESPHOME_REPO}/releases")
    stable = [
        {"tag": r["tag_name"], "date": r["published_at"][:10]}
        for r in data
        if not r["prerelease"] and not r["draft"]
    ]
    stable.sort(key=lambda r: r["date"])
    return stable


# ---------------------------------------------------------------------------
# Issue / PR cache
# ---------------------------------------------------------------------------

def _fetch_stream(repo: str, state: str, since: str | None = None) -> Generator[list[dict], None, None]:
    """Yield pages of open issues/PRs using cursor-based pagination.

    Uses item ID deduplication to handle the case where multiple items share the
    same updated_at timestamp, which would otherwise cause the `since` cursor to
    return the same page indefinitely.

    Yields one page (list of raw API items) at a time so callers can save
    incremental progress after each page.
    """
    seen_ids: set[int] = set()
    current_since = since
    per_page = 100
    total = 0

    while True:
        params: dict = {"state": state, "per_page": per_page, "sort": "updated", "direction": "asc"}
        if current_since:
            params["since"] = current_since

        items = get(f"repos/{repo}/issues", **params)
        if not items:
            break

        new_items = [item for item in items if item["number"] not in seen_ids]
        for item in items:
            seen_ids.add(item["number"])

        if new_items:
            total += len(new_items)
            print(f"  fetched {total} items ...", end="\r", flush=True)
            yield new_items

        if len(items) < per_page:
            break

        # If a full page added no new items, the cursor is stuck on a shared timestamp
        if not new_items:
            break

        current_since = items[-1]["updated_at"]


def _upsert(items_store: dict, raw_items: list[dict]) -> None:
    """Upsert raw API items into the cache store."""
    for item in raw_items:
        number = str(item["number"])
        components = [
            label["name"][len(_COMPONENT_PREFIX):]
            for label in item.get("labels", [])
            if label.get("name", "").startswith(_COMPONENT_PREFIX)
        ]
        items_store[number] = {
            "is_pr": "pull_request" in item,
            "title": item.get("title", ""),
            "components": components,
            "updated_at": item["updated_at"],
        }


def load_cache(path: Path) -> dict:
    """Load cache from disk, or return an empty cache."""
    if path.exists():
        return json.loads(path.read_text())
    return {"last_fetched_at": None, "items": {}}


def save_cache(cache: dict, path: Path) -> None:
    """Write cache to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2))


def update_cache(cache: dict, cache_path: Path | None = None, repo: str = ESPHOME_REPO) -> dict:
    """Fetch open issues/PRs from GitHub and merge into cache.

    Only open items are tracked. Saves incrementally after each page if
    cache_path is provided, so progress survives a kill or rate-limit timeout.

    Cold start (no last_fetched_at): fetches all open items.
    Incremental: fetches open items updated since last_fetched_at.
    """
    items_store = cache.setdefault("items", {})
    last_fetched = cache.get("last_fetched_at")

    if last_fetched is None:
        print("  cold start: fetching all open items ...")
        since = None
    else:
        print(f"  incremental fetch since {last_fetched[:10]} ...")
        since = last_fetched

    total = 0
    for page in _fetch_stream(repo, "open", since=since):
        _upsert(items_store, page)
        total += len(page)
        if cache_path:
            save_cache(cache, cache_path)

    print(f"  fetched {total} open items         ")

    cache["last_fetched_at"] = datetime.now(timezone.utc).isoformat()
    if cache_path:
        save_cache(cache, cache_path)
    return cache


def counts_from_cache(cache: dict) -> dict[str, dict]:
    """Derive per-component open issue/PR counts from the local cache."""
    counts: dict[str, dict] = {}
    for item in cache.get("items", {}).values():
        key = "open_prs" if item["is_pr"] else "open_issues"
        for component in item["components"]:
            if component not in counts:
                counts[component] = dict(_EMPTY_COUNTS)
            counts[component][key] += 1
    return counts
