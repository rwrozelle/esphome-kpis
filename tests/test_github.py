"""Tests for GitHub API helpers and issue/PR cache."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from esphome_kpis.github import (
    _CLOSED_RETENTION_DAYS,
    _cutoff_iso,
    _prune,
    _upsert,
    counts_from_cache,
    load_cache,
    releases,
    save_cache,
    update_cache,
)


def _iso(days_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _make_raw(number: int, state: str, is_pr: bool, components: list[str], days_ago: int = 1) -> dict:
    item: dict = {
        "number": number,
        "state": state,
        "labels": [{"name": f"component: {c}"} for c in components],
        "updated_at": _iso(days_ago),
    }
    if is_pr:
        item["pull_request"] = {"url": "https://example.com"}
    return item


class TestReleases:
    def test_filters_prereleases(self):
        mock_data = [
            {"tag_name": "2024.1.0", "published_at": "2024-01-17T10:00:00Z", "prerelease": False, "draft": False},
            {"tag_name": "2024.1.0b1", "published_at": "2024-01-10T10:00:00Z", "prerelease": True, "draft": False},
            {"tag_name": "2024.2.0", "published_at": "2024-02-14T10:00:00Z", "prerelease": False, "draft": False},
        ]
        with patch("esphome_kpis.github.paginate", return_value=mock_data):
            result = releases()
        tags = [r["tag"] for r in result]
        assert "2024.1.0b1" not in tags
        assert "2024.1.0" in tags

    def test_sorted_oldest_first(self):
        mock_data = [
            {"tag_name": "2024.2.0", "published_at": "2024-02-14T10:00:00Z", "prerelease": False, "draft": False},
            {"tag_name": "2024.1.0", "published_at": "2024-01-17T10:00:00Z", "prerelease": False, "draft": False},
        ]
        with patch("esphome_kpis.github.paginate", return_value=mock_data):
            result = releases()
        assert result[0]["tag"] == "2024.1.0"
        assert result[1]["tag"] == "2024.2.0"

    def test_date_truncated_to_day(self):
        mock_data = [
            {"tag_name": "2024.1.0", "published_at": "2024-01-17T10:30:45Z", "prerelease": False, "draft": False},
        ]
        with patch("esphome_kpis.github.paginate", return_value=mock_data):
            result = releases()
        assert result[0]["date"] == "2024-01-17"


class TestUpsert:
    def test_adds_new_item(self):
        store = {}
        _upsert(store, [_make_raw(1, "open", False, ["wifi"])])
        assert "1" in store
        assert store["1"]["state"] == "open"
        assert store["1"]["components"] == ["wifi"]
        assert store["1"]["is_pr"] is False

    def test_updates_existing_item(self):
        store = {"1": {"state": "open", "is_pr": False, "components": ["wifi"], "updated_at": _iso(5)}}
        _upsert(store, [_make_raw(1, "closed", False, ["wifi"], days_ago=1)])
        assert store["1"]["state"] == "closed"

    def test_multi_component_label(self):
        store = {}
        _upsert(store, [_make_raw(1, "open", False, ["wifi", "mqtt"])])
        assert store["1"]["components"] == ["wifi", "mqtt"]

    def test_no_component_label_stored_as_empty(self):
        item = {"number": 2, "state": "open", "labels": [{"name": "bugfix"}], "updated_at": _iso(1)}
        store = {}
        _upsert(store, [item])
        assert store["2"]["components"] == []

    def test_pr_flagged_correctly(self):
        store = {}
        _upsert(store, [_make_raw(3, "open", True, ["mqtt"])])
        assert store["3"]["is_pr"] is True


class TestPrune:
    def test_removes_old_closed(self):
        cutoff = _cutoff_iso()
        store = {
            "1": {"state": "closed", "updated_at": _iso(_CLOSED_RETENTION_DAYS + 10)},
            "2": {"state": "closed", "updated_at": _iso(30)},
            "3": {"state": "open", "updated_at": _iso(_CLOSED_RETENTION_DAYS + 10)},
        }
        pruned = _prune(store, cutoff)
        assert pruned == 1
        assert "1" not in store
        assert "2" in store
        assert "3" in store  # open items never pruned

    def test_returns_zero_when_nothing_to_prune(self):
        store = {"1": {"state": "closed", "updated_at": _iso(30)}}
        assert _prune(store, _cutoff_iso()) == 0


class TestCountsFromCache:
    def test_counts_open_issue(self):
        cache = {"items": {"1": {"state": "open", "is_pr": False, "components": ["wifi"], "updated_at": _iso(1)}}}
        result = counts_from_cache(cache)
        assert result["wifi"]["open_issues"] == 1
        assert result["wifi"]["closed_issues"] == 0

    def test_counts_closed_pr(self):
        cache = {"items": {"1": {"state": "closed", "is_pr": True, "components": ["mqtt"], "updated_at": _iso(1)}}}
        result = counts_from_cache(cache)
        assert result["mqtt"]["closed_prs"] == 1

    def test_multi_component_counted_for_each(self):
        item = {"state": "open", "is_pr": False, "components": ["wifi", "mqtt"], "updated_at": _iso(1)}
        cache = {"items": {"1": item}}
        result = counts_from_cache(cache)
        assert result["wifi"]["open_issues"] == 1
        assert result["mqtt"]["open_issues"] == 1

    def test_unlabeled_item_not_counted(self):
        cache = {"items": {"1": {"state": "open", "is_pr": False, "components": [], "updated_at": _iso(1)}}}
        result = counts_from_cache(cache)
        assert result == {}

    def test_all_four_keys_present(self):
        cache = {"items": {"1": {"state": "open", "is_pr": False, "components": ["dht"], "updated_at": _iso(1)}}}
        result = counts_from_cache(cache)
        assert set(result["dht"].keys()) == {"open_issues", "closed_issues", "open_prs", "closed_prs"}


class TestLoadSaveCache:
    def test_load_missing_returns_empty(self, tmp_path):
        cache = load_cache(tmp_path / "nonexistent.json")
        assert cache == {"last_fetched_at": None, "items": {}}

    def test_load_existing(self, tmp_path):
        path = tmp_path / "cache.json"
        data = {"last_fetched_at": "2026-01-01T00:00:00Z", "items": {"1": {"state": "open"}}}
        path.write_text(json.dumps(data))
        assert load_cache(path) == data

    def test_save_creates_dirs(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "cache.json"
        cache = {"last_fetched_at": None, "items": {}}
        save_cache(cache, path)
        assert path.exists()
        assert json.loads(path.read_text()) == cache


class TestUpdateCache:
    def _stream(self, items):
        """Return a _fetch_stream mock that yields items in one shot."""
        return lambda *a, **kw: items

    def test_cold_start_fetches_open_and_closed(self):
        open_items = [_make_raw(1, "open", False, ["wifi"])]
        closed_items = [_make_raw(2, "closed", False, ["mqtt"], days_ago=30)]
        cache = {"last_fetched_at": None, "items": {}}

        call_args = []
        def fake_stream(repo, state, since=None):
            call_args.append((state, since))
            return open_items if state == "open" else closed_items

        with patch("esphome_kpis.github._fetch_stream", side_effect=fake_stream):
            update_cache(cache)

        states = [a[0] for a in call_args]
        assert "open" in states
        assert "closed" in states
        assert "1" in cache["items"]
        assert "2" in cache["items"]
        assert cache["last_fetched_at"] is not None

    def test_incremental_fetches_all_since_last(self):
        cache = {
            "last_fetched_at": _iso(7),
            "items": {"1": {"state": "open", "is_pr": False, "components": ["wifi"], "updated_at": _iso(7)}},
        }
        new_item = _make_raw(2, "open", True, ["mqtt"])

        call_args = []
        def fake_stream(repo, state, since=None):
            call_args.append((state, since))
            return [new_item]

        with patch("esphome_kpis.github._fetch_stream", side_effect=fake_stream):
            update_cache(cache)

        assert call_args[0][0] == "all"
        assert call_args[0][1] is not None
        assert "2" in cache["items"]

    def test_prunes_old_closed_after_update(self):
        old_closed = {
            "state": "closed",
            "is_pr": False,
            "components": ["dht"],
            "updated_at": _iso(_CLOSED_RETENTION_DAYS + 10),
        }
        cache = {"last_fetched_at": _iso(1), "items": {"99": old_closed}}

        with patch("esphome_kpis.github._fetch_stream", return_value=[]):
            update_cache(cache)

        assert "99" not in cache["items"]
