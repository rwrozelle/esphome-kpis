"""Main KPI collection entry point."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import github, repo

ESPHOME_REPO_URL = "https://github.com/esphome/esphome.git"


def _clone_esphome(dest: Path) -> None:
    print(f"Cloning esphome into {dest} ...")
    subprocess.run(
        ["git", "clone", "--depth=1", "--no-single-branch", ESPHOME_REPO_URL, str(dest)],
        check=True,
    )
    # Fetch full history for log queries (not --depth shallow)
    subprocess.run(["git", "fetch", "--unshallow"], cwd=dest, check=True)


def collect(esphome_root: Path, component_filter: list[str] | None = None) -> dict:
    print("Fetching release list from GitHub ...")
    releases = github.releases()

    print("Bulk-fetching all issue and PR counts from GitHub ...")
    issue_counts = github.fetch_all_issue_counts()

    components = repo.component_names(esphome_root)
    if component_filter:
        components = [c for c in components if c in component_filter]

    print(f"Collecting KPIs for {len(components)} components ...")
    results = {}

    for i, component in enumerate(components, 1):
        print(f"  [{i}/{len(components)}] {component}", flush=True)

        first_date = repo.first_commit_date(esphome_root, component)
        last_date = repo.last_commit_date(esphome_root, component)
        gh_counts = issue_counts.get(component, github._EMPTY_COUNTS)

        results[component] = {
            "version_created": repo.date_to_version(first_date, releases),
            "version_last_modified": repo.date_to_version(last_date, releases),
            "last_commit_date": last_date,
            "entity_types": repo.entity_types(esphome_root, component),
            **repo.platform_info(esphome_root, component),
            **repo.component_tests(esphome_root, component),
            **repo.codeowners_info(esphome_root, component),
            **gh_counts,
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "esphome_releases": releases,
        "components": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect ESPHome component KPIs")
    parser.add_argument(
        "--esphome-root",
        type=Path,
        default=None,
        help="Path to local esphome repo (clones if not provided)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/components.json"),
        help="Output JSON file path",
    )
    parser.add_argument(
        "--components",
        nargs="+",
        metavar="NAME",
        help="Collect only these components (for testing)",
    )
    args = parser.parse_args()

    esphome_root = args.esphome_root
    tmp_dir = None

    if esphome_root is None:
        tmp_dir = tempfile.mkdtemp(prefix="esphome-kpis-")
        esphome_root = Path(tmp_dir)
        _clone_esphome(esphome_root)
    elif not (esphome_root / "esphome" / "components").exists():
        print(f"Error: {esphome_root} does not look like an esphome repo", file=sys.stderr)
        sys.exit(1)

    data = collect(esphome_root, component_filter=args.components)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2))
    print(f"\nWrote {len(data['components'])} components to {args.output}")


if __name__ == "__main__":
    main()
