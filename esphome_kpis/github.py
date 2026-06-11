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


def issues_and_prs(component: str) -> dict:
    """Return open/closed issue and PR counts for a component label."""
    label = f"component: {component}"
    result = {"open_issues": 0, "closed_issues": 0, "open_prs": 0, "closed_prs": 0}

    for state in ("open", "closed"):
        items = paginate(
            f"repos/{ESPHOME_REPO}/issues",
            labels=label,
            state=state,
        )
        for item in items:
            if "pull_request" in item:
                key = f"{state}_prs"
            else:
                key = f"{state}_issues"
            result[key] += 1

    return result
