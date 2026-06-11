"""Tests for GitHub API helpers."""

from unittest.mock import patch

from esphome_kpis.github import releases


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
