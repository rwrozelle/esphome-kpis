"""GitHub API helpers with rate-limit awareness."""

from __future__ import annotations

import os
import time

import requests

GITHUB_API = "https://api.github.com"
ESPHOME_REPO = "esphome/esphome"


def _session() -> requests.Session:
    s = requests.Session()
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    s.headers["Accept"] = "application/vnd.github+json"
    s.headers["X-GitHub-Api-Version"] = "2022-11-28"
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


_COMPONENT_PREFIX = "component: "
_EMPTY_COUNTS = {"open_issues": 0, "closed_issues": 0, "open_prs": 0, "closed_prs": 0}


def fetch_all_issue_counts(repo: str = ESPHOME_REPO) -> dict[str, dict]:
    """Fetch all issues and PRs in one bulk pass, return counts keyed by component.

    Reduces ~1400 per-component API calls to a single paginated stream.
    Only reads state, labels, and pull_request presence per item.
    """
    counts: dict[str, dict] = {}
    page = 1
    per_page = 100
    total = 0

    while True:
        items = get(
            f"repos/{repo}/issues",
            state="all",
            per_page=per_page,
            page=page,
        )
        if not items:
            break

        for item in items:
            state = item["state"]
            is_pr = "pull_request" in item
            key = f"{state}_{'prs' if is_pr else 'issues'}"
            for label in item.get("labels", []):
                name = label.get("name", "")
                if name.startswith(_COMPONENT_PREFIX):
                    component = name[len(_COMPONENT_PREFIX):]
                    if component not in counts:
                        counts[component] = dict(_EMPTY_COUNTS)
                    counts[component][key] += 1

        total += len(items)
        print(f"  fetched {total} issues/PRs ...", end="\r", flush=True)
        if len(items) < per_page:
            break
        page += 1

    print(f"  fetched {total} issues/PRs total")
    return counts
