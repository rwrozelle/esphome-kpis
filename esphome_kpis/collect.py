"""Main KPI collection entry point."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import github, repo

_BRACKET_RE = re.compile(r"\[([^\]]+)\]")

ESPHOME_REPO_URL = "https://github.com/esphome/esphome.git"
DEFAULT_CACHE = Path("data/github_cache.json")


def _clone_esphome(dest: Path) -> None:
    print(f"Cloning esphome into {dest} ...")
    subprocess.run(
        ["git", "clone", "--depth=1", "--no-single-branch", ESPHOME_REPO_URL, str(dest)],
        check=True,
    )
    subprocess.run(["git", "fetch", "--unshallow"], cwd=dest, check=True)


def _resolve_components_from_titles(cache: dict, known: set[str]) -> int:
    """Fill in missing components for unlabeled items by scanning issue titles.

    Three strategies, applied together:
    - [bracket] notation anywhere in title
    - Underscore-containing names (e.g. online_image) anywhere in title — low false-positive rate
    - Short single-word names only at the very start of the title (before a separator)

    Validates all names against the known component set.
    Returns number of items updated.
    """
    # Pre-compile patterns once per call (known set is stable per run)
    underscore_pats = {c: re.compile(r"\b" + re.escape(c) + r"\b", re.IGNORECASE) for c in known if "_" in c}
    start_pats = {c: re.compile(r"^" + re.escape(c) + r"[\s:/\-\[,]", re.IGNORECASE) for c in known if "_" not in c}

    updated = 0
    for item in cache.get("items", {}).values():
        if item["components"]:
            continue
        title = item.get("title", "")
        found: set[str] = set()
        for m in _BRACKET_RE.findall(title):
            if m.lower() in known:
                found.add(m.lower())
        for c, pat in underscore_pats.items():
            if pat.search(title):
                found.add(c)
        for c, pat in start_pats.items():
            if pat.search(title):
                found.add(c)
        if found:
            item["components"] = sorted(found)
            updated += 1
    return updated


def _load_previous(output_path: Path | None) -> tuple[dict, str | None]:
    """Load previous output JSON. Returns (components dict, generated_at timestamp)."""
    if output_path and output_path.exists():
        try:
            prev = json.loads(output_path.read_text())
            return prev.get("components", {}), prev.get("generated_at")
        except Exception:
            pass
    return {}, None


def collect(
    esphome_root: Path,
    cache_path: Path,
    output_path: Path | None = None,
    component_filter: list[str] | None = None,
) -> dict:
    print("Fetching release list from GitHub ...")
    releases = github.releases()

    print("Updating GitHub issue/PR cache ...")
    cache = github.load_cache(cache_path)
    github.update_cache(cache, cache_path=cache_path)
    github.save_cache(cache, cache_path)
    print(f"  cache saved to {cache_path} ({len(cache['items'])} items)")

    print("Updating esphome.io docs tree cache ...")
    github.update_docs_cache(cache, cache_path=cache_path)
    docs_types = github.docs_component_types(cache)
    docs_urls = github.docs_component_urls(cache)

    components = repo.component_names(esphome_root)
    known = set(components)
    resolved = _resolve_components_from_titles(cache, known)
    if resolved:
        print(f"  resolved {resolved} unlabeled items from title brackets")

    issue_counts = github.counts_from_cache(cache)
    if component_filter:
        components = [c for c in components if c in component_filter]

    # Load previous run to skip git work for unchanged components
    prev_components, prev_generated_at = _load_previous(output_path)
    if prev_generated_at and not component_filter:
        changed = repo.changed_components_since(esphome_root, prev_generated_at)
        if changed is None:
            print("  CODEOWNERS changed — recomputing codeowners for all components")
            codeowners_changed = True
            changed = set()  # will be populated per-component via git log
        else:
            codeowners_changed = False
        reuse_count = sum(1 for c in components if c in prev_components and c not in changed)
        print(f"  {len(changed)} components changed since last run, reusing {reuse_count} unchanged")
    else:
        changed = None  # first run or filtered run — compute everything
        codeowners_changed = False

    print(f"Collecting KPIs for {len(components)} components ...")
    results = {}

    for i, component in enumerate(components, 1):
        prev = prev_components.get(component, {})
        gh_counts = issue_counts.get(component, dict(github._EMPTY_COUNTS))

        # Reuse all cached git/file values if component hasn't changed
        if changed is not None and component not in changed and prev:
            print(f"  [{i}/{len(components)}] {component} (cached)", flush=True)
            results[component] = {
                **prev,
                **gh_counts,
            }
            # Re-run codeowners if that file changed
            if codeowners_changed:
                results[component].update(repo.codeowners_info(esphome_root, component))
            continue

        print(f"  [{i}/{len(components)}] {component}", flush=True)

        first_date = repo.first_commit_date(esphome_root, component)
        last_date = repo.last_commit_date(esphome_root, component)

        results[component] = {
            "version_created": repo.date_to_version(first_date, releases),
            "version_last_modified": repo.date_to_version(last_date, releases),
            "last_commit_date": last_date,
            "type": repo.component_type(esphome_root, component, docs_types),
            "docs_url": docs_urls.get(component),
            **repo.platform_info(esphome_root, component),
            **repo.component_tests(esphome_root, component),
            **repo.codeowners_info(esphome_root, component),
            **gh_counts,
        }

    # Tally attribution coverage for the footer note in rendered output.
    # Three buckets per type:
    #   known   — attributed to a component that exists in this repo (shown in table)
    #   new     — attributed to a name not in this repo (new-component PRs/issues)
    #   none    — no attribution found at all
    def _tally(is_pr: bool) -> tuple[int, int, int]:
        total = known_c = new_c = 0
        for v in cache.get("items", {}).values():
            if v["is_pr"] != is_pr:
                continue
            total += 1
            comps = v.get("components", [])
            if not comps:
                pass  # none bucket
            elif any(c in known for c in comps):
                known_c += 1
            else:
                new_c += 1
        return total, known_c, new_c

    total_issues, known_issues, new_issues = _tally(False)
    total_prs,    known_prs,    new_prs    = _tally(True)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "esphome_releases": releases,
        "issue_stats": {
            "total_issues":      total_issues,
            "known_issues":      known_issues,
            "new_comp_issues":   new_issues,
            "unattr_issues":     total_issues - known_issues - new_issues,
            "total_prs":         total_prs,
            "known_prs":         known_prs,
            "new_comp_prs":      new_prs,
            "unattr_prs":        total_prs - known_prs - new_prs,
        },
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
        "--cache",
        type=Path,
        default=DEFAULT_CACHE,
        help="GitHub issue/PR cache file path",
    )
    parser.add_argument(
        "--components",
        nargs="+",
        metavar="NAME",
        help="Collect only these components (for testing)",
    )
    args = parser.parse_args()

    esphome_root = args.esphome_root

    if esphome_root is None:
        tmp_dir = tempfile.mkdtemp(prefix="esphome-kpis-")
        esphome_root = Path(tmp_dir)
        _clone_esphome(esphome_root)
    elif not (esphome_root / "esphome" / "components").exists():
        print(f"Error: {esphome_root} does not look like an esphome repo", file=sys.stderr)
        sys.exit(1)

    data = collect(esphome_root, args.cache, output_path=args.output, component_filter=args.components)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2))
    print(f"\nWrote {len(data['components'])} components to {args.output}")


if __name__ == "__main__":
    main()
