"""Local ESPHome repo inspection — git history, tests, CODEOWNERS, platforms."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def component_names(esphome_root: Path) -> list[str]:
    """Return sorted list of component names from esphome/components/."""
    components_dir = esphome_root / "esphome" / "components"
    return sorted(
        d.name
        for d in components_dir.iterdir()
        if d.is_dir() and not d.name.startswith("_")
    )


def first_commit_date(esphome_root: Path, component: str) -> str | None:
    """Return ISO date of the first commit touching this component."""
    path = f"esphome/components/{component}"
    out = _git(
        ["log", "--diff-filter=A", "--follow", "--format=%ci", "--reverse", "--", path],
        esphome_root,
    )
    if not out:
        return None
    return out.split("\n")[0][:10]


def last_commit_date(esphome_root: Path, component: str) -> str | None:
    """Return ISO date of the most recent commit touching this component."""
    path = f"esphome/components/{component}"
    out = _git(
        ["log", "-1", "--format=%ci", "--", path],
        esphome_root,
    )
    return out[:10] if out else None


ENTITY_TYPES = frozenset({
    "alarm_control_panel",
    "binary_sensor",
    "button",
    "climate",
    "cover",
    "event",
    "fan",
    "light",
    "lock",
    "media_player",
    "number",
    "output",
    "select",
    "sensor",
    "switch",
    "text_sensor",
    "update",
    "valve",
})


def entity_types(esphome_root: Path, component: str) -> list[str]:
    """Return entity types provided by this component (e.g. sensor, switch)."""
    comp_dir = esphome_root / "esphome" / "components" / component
    found = set()
    for child in comp_dir.iterdir():
        name = child.stem if child.is_file() and child.suffix == ".py" else child.name
        if name in ENTITY_TYPES:
            found.add(name)
    return sorted(found)


def platform_coverage(esphome_root: Path, component: str) -> list[str]:
    """Return list of platform subdirectories under the component."""
    comp_dir = esphome_root / "esphome" / "components" / component
    known_platforms = {"esp32", "esp8266", "rp2040", "libretiny", "host", "zephyr", "bk72xx", "rtl87xx"}
    return sorted(
        d.name
        for d in comp_dir.iterdir()
        if d.is_dir() and d.name in known_platforms
    )


def component_tests(esphome_root: Path, component: str) -> dict:
    """Return test file presence and count."""
    test_dir = esphome_root / "tests" / "components" / component
    if not test_dir.exists():
        return {"has_tests": False, "test_file_count": 0}
    yaml_files = list(test_dir.rglob("*.yaml"))
    return {"has_tests": True, "test_file_count": len(yaml_files)}


def codeowners_info(esphome_root: Path, component: str) -> dict:
    """Return CODEOWNERS presence and owner count for this component."""
    codeowners_path = esphome_root / ".github" / "CODEOWNERS"
    if not codeowners_path.exists():
        return {"has_codeowners": False, "codeowners_count": 0, "codeowners": []}

    pattern = f"esphome/components/{component}"
    owners: list[str] = []
    for line in codeowners_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts and parts[0].rstrip("/") == pattern:
            owners = parts[1:]
            break

    return {
        "has_codeowners": len(owners) > 0,
        "codeowners_count": len(owners),
        "codeowners": owners,
    }


def date_to_version(date: str | None, releases: list[dict]) -> str | None:
    """Map a commit date (YYYY-MM-DD) to the earliest release on or after that date."""
    if not date or not releases:
        return None
    for release in releases:
        if release["date"] >= date:
            return release["tag"]
    return releases[-1]["tag"]
