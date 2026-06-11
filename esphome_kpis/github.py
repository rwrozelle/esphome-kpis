"""GitHub API helpers with rate-limit awareness and local issue/PR cache."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

GITHUB_API = "https://api.github.com"
ESPHOME_REPO = "esphome/esphome"

_COMPONENT_PREFIX = "component: "
_EMPTY_COUNTS = {"open_issues": 0, "closed_issues": 0, "open_prs": 0, "closed_prs": 0}
_CLOSED_RETENTION_DAYS = 365


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

def _cutoff_iso() -> str:
    """ISO timestamp for now minus _CLOSED_RETENTION_DAYS."""
    return (datetime.now(timezone.utc) - timedelta(days=_CLOSED_RETENTION_DAYS)).isoformat()


def _fetch_stream(repo: str, state: str, since: str | None = None) -> list[dict]:
    """Fetch issues/PRs using cursor-based pagination to bypass the 1000-item cap.

    Advances the `since` cursor using the last item's updated_at so each
    request stays within GitHub's per-query limit.
    """
    results = []
    current_since = since
    per_page = 100

    while True:
        params: dict = {"state": state, "per_page": per_page, "sort": "updated", "direction": "asc"}
        if current_since:
            params["since"] = current_since

        items = get(f"repos/{repo}/issues", **params)
        if not items:
            break

        results.extend(items)
        print(f"  fetched {len(results)} items ({state}) ...", end="\r", flush=True)

        if len(items) < per_page:
            break

        current_since = items[-1]["updated_at"]

    return results


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
            "state": item["state"],
            "is_pr": "pull_request" in item,
            "components": components,
            "updated_at": item["updated_at"],
        }


def _prune(items_store: dict, cutoff: str) -> int:
    """Remove closed items older than cutoff. Returns number pruned."""
    stale = [k for k, v in items_store.items() if v["state"] == "closed" and v["updated_at"] < cutoff]
    for k in stale:
        del items_store[k]
    return len(stale)


def load_cache(path: Path) -> dict:
    """Load cache from disk, or return an empty cache."""
    if path.exists():
        return json.loads(path.read_text())
    return {"last_fetched_at": None, "items": {}}


def save_cache(cache: dict, path: Path) -> None:
    """Write cache to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2))


def update_cache(cache: dict, repo: str = ESPHOME_REPO) -> dict:
    """Fetch new/changed items from GitHub and merge into cache.

    Cold start (no last_fetched_at):
      - Fetch all open items (no time limit)
      - Fetch closed items updated in the last 365 days

    Incremental (cache exists):
      - Fetch all items (open + closed) updated since last_fetched_at
        This catches state changes (open -> closed) as well as new items.

    After fetching, prune closed items older than 365 days and record
    last_fetched_at = now.
    """
    cutoff = _cutoff_iso()
    items_store = cache.setdefault("items", {})
    last_fetched = cache.get("last_fetched_at")

    if last_fetched is None:
        print("  cold start: fetching all open items ...")
        open_items = _fetch_stream(repo, "open")
        print(f"  fetched {len(open_items)} open items         ")

        print("  cold start: fetching closed items (last 365 days) ...")
        closed_items = _fetch_stream(repo, "closed", since=cutoff)
        print(f"  fetched {len(closed_items)} closed items        ")

        _upsert(items_store, open_items + closed_items)
    else:
        print(f"  incremental fetch since {last_fetched[:10]} ...")
        updated = _fetch_stream(repo, "all", since=last_fetched)
        print(f"  fetched {len(updated)} updated items         ")
        _upsert(items_store, updated)

    pruned = _prune(items_store, cutoff)
    if pruned:
        print(f"  pruned {pruned} closed items older than 365 days")

    cache["last_fetched_at"] = datetime.now(timezone.utc).isoformat()
    return cache


def counts_from_cache(cache: dict) -> dict[str, dict]:
    """Derive per-component open/closed issue/PR counts from the local cache."""
    counts: dict[str, dict] = {}
    for item in cache.get("items", {}).values():
        state = item["state"]
        key = f"{state}_{'prs' if item['is_pr'] else 'issues'}"
        for component in item["components"]:
            if component not in counts:
                counts[component] = dict(_EMPTY_COUNTS)
            counts[component][key] += 1
    return counts
