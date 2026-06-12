"""Local ESPHome repo inspection — git history, tests, CODEOWNERS, platforms."""

from __future__ import annotations

import re
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


def changed_components_since(esphome_root: Path, since: str) -> set[str] | None:
    """Return set of component names with commits since `since` (ISO timestamp).

    Also returns None if CODEOWNERS changed (caller should recompute all codeowners).
    Returns an empty set if nothing changed.
    """
    out = _git(
        ["log", f"--since={since}", "--name-only", "--format="],
        esphome_root,
    )
    components: set[str] = set()
    codeowners_changed = False
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if line == ".github/CODEOWNERS":
            codeowners_changed = True
        parts = line.split("/")
        if len(parts) >= 3 and parts[0] == "esphome" and parts[1] == "components":
            components.add(parts[2])
    return None if codeowners_changed else components


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


KNOWN_PLATFORMS = frozenset({"esp32", "esp8266", "rp2040", "libretiny", "host", "zephyr", "bk72xx", "rtl87xx"})

_IFDEF_RE = re.compile(r"#\s*ifdef\s+(USE_\w+)")
_PLATFORM_SUFFIX = {f"USE_{p.upper()}": p for p in KNOWN_PLATFORMS}


_TOP_LINES = 5


def platform_info(esphome_root: Path, component: str) -> dict:
    """Return supported_platforms for a component.

    Scans .h and .cpp files for USE_<PLATFORM> #ifdef guards in the first
    5 lines. A guard that early means the entire file is platform-specific.
    Mid-file guards (conditional sections within a generic file) are ignored.
    supported_platforms: ["all"] if no top-of-file guards found, else those platforms.
    """
    comp_dir = esphome_root / "esphome" / "components" / component

    positive: set[str] = set()

    for f in comp_dir.iterdir():
        if f.suffix not in (".h", ".cpp"):
            continue
        try:
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines[:_TOP_LINES]:
            m = _IFDEF_RE.search(line)
            if m:
                plat = _PLATFORM_SUFFIX.get(m.group(1))
                if plat:
                    positive.add(plat)

    return {"supported_platforms": sorted(positive) if positive else ["all"]}


def component_tests(esphome_root: Path, component: str) -> dict:
    """Return test file presence and count."""
    test_dir = esphome_root / "tests" / "components" / component
    if not test_dir.exists():
        return {"has_tests": False, "test_file_count": 0}
    yaml_files = list(test_dir.rglob("*.yaml"))
    return {"has_tests": True, "test_file_count": len(yaml_files)}


def codeowners_info(esphome_root: Path, component: str) -> dict:
    """Return CODEOWNERS presence and owner count for this component."""
    codeowners_path = esphome_root / "CODEOWNERS"
    if not codeowners_path.exists():
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
        if parts and parts[0].rstrip("/*") == pattern:
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
