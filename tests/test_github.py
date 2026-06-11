"""Tests for GitHub API helpers."""

from unittest.mock import patch

from esphome_kpis.github import fetch_all_issue_counts, releases


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
        assert "2024.2.0" in tags

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


class TestFetchAllIssueCounts:
    def _make_item(self, state, is_pr, components):
        item = {
            "state": state,
            "labels": [{"name": f"component: {c}"} for c in components],
        }
        if is_pr:
            item["pull_request"] = {"url": "https://example.com"}
        return item

    def test_counts_open_issues(self):
        items = [self._make_item("open", False, ["wifi"])]
        with patch("esphome_kpis.github.get", return_value=items):
            result = fetch_all_issue_counts()
        assert result["wifi"]["open_issues"] == 1
        assert result["wifi"]["closed_issues"] == 0

    def test_counts_closed_prs(self):
        items = [self._make_item("closed", True, ["mqtt"])]
        with patch("esphome_kpis.github.get", return_value=items):
            result = fetch_all_issue_counts()
        assert result["mqtt"]["closed_prs"] == 1
        assert result["mqtt"]["open_prs"] == 0

    def test_item_with_multiple_component_labels(self):
        items = [self._make_item("open", False, ["wifi", "mqtt"])]
        with patch("esphome_kpis.github.get", return_value=items):
            result = fetch_all_issue_counts()
        assert result["wifi"]["open_issues"] == 1
        assert result["mqtt"]["open_issues"] == 1

    def test_item_with_no_component_label_ignored(self):
        item = {"state": "open", "labels": [{"name": "bugfix"}]}
        with patch("esphome_kpis.github.get", return_value=[item]):
            result = fetch_all_issue_counts()
        assert result == {}

    def test_unknown_component_gets_zero_defaults(self):
        items = [self._make_item("open", False, ["dht"])]
        with patch("esphome_kpis.github.get", return_value=items):
            result = fetch_all_issue_counts()
        assert set(result["dht"].keys()) == {"open_issues", "closed_issues", "open_prs", "closed_prs"}
