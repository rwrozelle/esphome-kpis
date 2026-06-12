"""Tests for GitHub API helpers and issue/PR cache."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from esphome_kpis.github import (
    _upsert,
    counts_from_cache,
    load_cache,
    releases,
    save_cache,
    update_cache,
)


def _iso(days_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _make_raw(number: int, is_pr: bool, components: list[str], days_ago: int = 1) -> dict:
    item: dict = {
        "number": number,
        "state": "open",
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
        _upsert(store, [_make_raw(1, False, ["wifi"])])
        assert "1" in store
        assert store["1"]["components"] == ["wifi"]
        assert store["1"]["is_pr"] is False

    def test_updates_existing_item(self):
        store = {"1": {"is_pr": False, "components": ["wifi"], "updated_at": _iso(5)}}
        _upsert(store, [_make_raw(1, False, ["wifi"], days_ago=1)])
        assert store["1"]["updated_at"] > _iso(3)

    def test_multi_component_label(self):
        store = {}
        _upsert(store, [_make_raw(1, False, ["wifi", "mqtt"])])
        assert store["1"]["components"] == ["wifi", "mqtt"]

    def test_no_component_label_stored_as_empty(self):
        item = {"number": 2, "state": "open", "labels": [{"name": "bugfix"}], "updated_at": _iso(1)}
        store = {}
        _upsert(store, [item])
        assert store["2"]["components"] == []

    def test_pr_flagged_correctly(self):
        store = {}
        _upsert(store, [_make_raw(3, True, ["mqtt"])])
        assert store["3"]["is_pr"] is True

    def test_no_state_stored(self):
        store = {}
        _upsert(store, [_make_raw(1, False, ["wifi"])])
        assert "state" not in store["1"]


class TestCountsFromCache:
    def test_counts_open_issue(self):
        cache = {"items": {"1": {"is_pr": False, "components": ["wifi"], "updated_at": _iso(1)}}}
        result = counts_from_cache(cache)
        assert result["wifi"]["open_issues"] == 1
        assert result["wifi"]["open_prs"] == 0

    def test_counts_open_pr(self):
        cache = {"items": {"1": {"is_pr": True, "components": ["mqtt"], "updated_at": _iso(1)}}}
        result = counts_from_cache(cache)
        assert result["mqtt"]["open_prs"] == 1
        assert result["mqtt"]["open_issues"] == 0

    def test_multi_component_counted_for_each(self):
        item = {"is_pr": False, "components": ["wifi", "mqtt"], "updated_at": _iso(1)}
        cache = {"items": {"1": item}}
        result = counts_from_cache(cache)
        assert result["wifi"]["open_issues"] == 1
        assert result["mqtt"]["open_issues"] == 1

    def test_unlabeled_item_not_counted(self):
        cache = {"items": {"1": {"is_pr": False, "components": [], "updated_at": _iso(1)}}}
        result = counts_from_cache(cache)
        assert result == {}

    def test_only_two_keys_present(self):
        cache = {"items": {"1": {"is_pr": False, "components": ["dht"], "updated_at": _iso(1)}}}
        result = counts_from_cache(cache)
        assert set(result["dht"].keys()) == {"open_issues", "open_prs"}


class TestLoadSaveCache:
    def test_load_missing_returns_empty(self, tmp_path):
        cache = load_cache(tmp_path / "nonexistent.json")
        assert cache == {"last_fetched_at": None, "items": {}}

    def test_load_existing(self, tmp_path):
        path = tmp_path / "cache.json"
        data = {"last_fetched_at": "2026-01-01T00:00:00Z", "items": {"1": {"is_pr": False}}}
        path.write_text(json.dumps(data))
        assert load_cache(path) == data

    def test_save_creates_dirs(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "cache.json"
        cache = {"last_fetched_at": None, "items": {}}
        save_cache(cache, path)
        assert path.exists()
        assert json.loads(path.read_text()) == cache


class TestUpdateCache:
    def _make_stream(self, pages: list[list[dict]]):
        """Return a _fetch_stream side_effect that yields the given pages."""
        def fake_stream(repo, state, since=None):
            yield from pages
        return fake_stream

    def test_cold_start_fetches_open(self, tmp_path):
        items = [_make_raw(1, False, ["wifi"])]
        cache = {"last_fetched_at": None, "items": {}}
        cache_path = tmp_path / "cache.json"

        with patch("esphome_kpis.github._fetch_stream", side_effect=self._make_stream([items])):
            update_cache(cache, cache_path=cache_path)

        assert "1" in cache["items"]
        assert cache["last_fetched_at"] is not None

    def test_cold_start_passes_no_since(self):
        cache = {"last_fetched_at": None, "items": {}}
        call_args = []

        def fake_stream(repo, state, since=None):
            call_args.append(since)
            return iter([])

        with patch("esphome_kpis.github._fetch_stream", side_effect=fake_stream):
            update_cache(cache)

        assert call_args[0] is None

    def test_incremental_passes_last_fetched_as_since(self):
        last = _iso(7)
        cache = {"last_fetched_at": last, "items": {}}
        call_args = []

        def fake_stream(repo, state, since=None):
            call_args.append(since)
            return iter([])

        with patch("esphome_kpis.github._fetch_stream", side_effect=fake_stream):
            update_cache(cache)

        assert call_args[0] == last

    def test_saves_incrementally_after_each_page(self, tmp_path):
        page1 = [_make_raw(1, False, ["wifi"])]
        page2 = [_make_raw(2, True, ["mqtt"])]
        cache = {"last_fetched_at": None, "items": {}}
        cache_path = tmp_path / "cache.json"
        saves_at = []

        original_save = save_cache

        def tracking_save(c, p):
            saves_at.append(len(c["items"]))
            original_save(c, p)

        with patch("esphome_kpis.github._fetch_stream", side_effect=self._make_stream([page1, page2])):
            with patch("esphome_kpis.github.save_cache", side_effect=tracking_save):
                update_cache(cache, cache_path=cache_path)

        # saved after page1 (1 item), after page2 (2 items), and final save
        assert saves_at[0] == 1
        assert saves_at[1] == 2

    def test_no_cache_path_does_not_save_mid_run(self):
        items = [_make_raw(1, False, ["wifi"])]
        cache = {"last_fetched_at": None, "items": {}}

        with patch("esphome_kpis.github._fetch_stream", side_effect=self._make_stream([items])):
            with patch("esphome_kpis.github.save_cache") as mock_save:
                update_cache(cache, cache_path=None)

        mock_save.assert_not_called()
