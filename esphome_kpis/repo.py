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
    """Return sorted list of git-tracked component names from esphome/components/.

    Only includes components whose __init__.py is tracked by git, filtering out
    local WIP directories that are not part of the official repo.
    """
    out = _git(
        ["ls-files", "esphome/components/"],
        esphome_root,
    )
    tracked: set[str] = set()
    for line in out.splitlines():
        parts = line.split("/")
        if len(parts) >= 4 and parts[0] == "esphome" and parts[1] == "components":
            tracked.add(parts[2])
    return sorted(tracked)


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


COMPONENT_TYPES = frozenset({
    # HA integration entity types
    "alarm_control_panel",
    "binary_sensor",
    "button",
    "climate",
    "cover",
    "datetime",
    "event",
    "fan",
    "light",
    "lock",
    "media_player",
    "number",
    "output",
    "select",
    "sensor",
    "speaker",
    "stepper",
    "switch",
    "text",
    "text_sensor",
    "touchscreen",
    "update",
    "valve",
    "water_heater",
    # ESPHome-specific platform types
    "display",
})

# Matches dot-path imports: 'from esphome.components.<type>...'
_DOTPATH_IMPORT_RE = re.compile(
    r"from\s+esphome\.components\.(" + "|".join(sorted(COMPONENT_TYPES)) + r")\b"
)
# Matches direct imports: 'from esphome.components import <type>[, <type>...]'
_DIRECT_IMPORT_RE = re.compile(r"from\s+esphome\.components\s+import\s+([^\n\\]+(\\[^\n]*\n[^\n]+)*)")

# Hardcoded taxonomy for infrastructure/platform components that have no entity-type
# files/dirs and don't import from entity-type modules.
COMPONENT_TAXONOMY: dict[str, list[str]] = {
    # Hardware platforms
    "bk72xx": ["platform"],
    "esp32": ["platform"],
    "esp8266": ["platform"],
    "host": ["platform"],
    "libretiny": ["platform"],
    "ln882x": ["platform"],
    "nrf52": ["platform"],
    "rp2040": ["platform"],
    "rtl87xx": ["platform"],
    "zephyr": ["platform"],
    # Communication buses
    "canbus": ["canbus"],
    "esp32_can": ["canbus"],
    "i2c": ["i2c"],
    "i2c_device": ["i2c"],
    "modbus": ["modbus"],
    "modbus_server": ["modbus"],
    "one_wire": ["one_wire"],
    "spi": ["spi"],
    "spi_device": ["spi"],
    "uart": ["uart"],
    # Core networking / HA integration
    "api": ["api"],
    "captive_portal": ["network"],
    "espnow": ["network"],
    "ethernet": ["ethernet"],
    "logger": ["logger"],
    "mdns": ["network"],
    "mqtt": ["mqtt"],
    "network": ["network"],
    "openthread": ["network"],
    "ota": ["ota"],
    "prometheus": ["network"],
    "sntp": ["time"],
    "syslog": ["network"],
    "time": ["time"],
    "web_server": ["web_server"],
    "web_server_base": ["web_server"],
    "web_server_idf": ["web_server"],
    "wifi": ["wifi"],
    "zephyr_mcumgr": ["ota"],
    # Bluetooth
    "ble_nus": ["bluetooth"],
    "bluetooth_proxy": ["bluetooth"],
    "bt_proxy": ["bluetooth"],
    "esp32_ble": ["bluetooth"],
    "esp32_ble_beacon": ["bluetooth"],
    "esp32_ble_client": ["bluetooth"],
    "esp32_ble_server": ["bluetooth"],
    "esp32_ble_tracker": ["bluetooth"],
    "rp2040_ble": ["bluetooth"],
    "zephyr_ble_server": ["bluetooth"],
    # Display infrastructure (no display/ subdir)
    "animation": ["display"],
    "color": ["display"],
    "font": ["display"],
    "graph": ["display"],
    "image": ["display"],
    "online_image": ["display"],
    "qr_code": ["display"],
    "runtime_image": ["display"],
    # Audio
    "aic3204": ["audio"],
    "audio": ["audio"],
    "audio_adc": ["audio"],
    "audio_dac": ["audio"],
    "audio_file": ["audio"],
    "audio_http": ["audio"],
    "es7210": ["audio"],
    "es7243e": ["audio"],
    "es8156": ["audio"],
    "es8311": ["audio"],
    "microphone": ["audio"],
    "pcm5122": ["audio"],
    # Camera
    "camera": ["camera"],
    "camera_encoder": ["camera"],
    "esp32_camera": ["camera"],
    "esp32_camera_web_server": ["camera"],
    # Radio / RF
    "cc1101": ["rf"],
    "infrared": ["rf"],
    "radio_frequency": ["rf"],
    "rf_bridge": ["rf"],
    "sx126x": ["rf"],
    "sx127x": ["rf"],
    # Core infrastructure
    "dashboard_import": ["core"],
    "deep_sleep": ["core"],
    "demo": ["core"],
    "esphome": ["core"],
    "external_components": ["core"],
    "factory_reset": ["core"],
    "globals": ["core"],
    "interval": ["core"],
    "packages": ["core"],
    "preferences": ["core"],
    "psram": ["core"],
    "runtime_stats": ["core"],
    "safe_mode": ["core"],
    "script": ["core"],
    "substitutions": ["core"],
    "watchdog": ["core"],
    # GPIO expanders (I2C/SPI attached IO chips)
    "ch422g": ["gpio_expander"],
    "ch423": ["gpio_expander"],
    "gpio_expander": ["gpio_expander"],
    "mcp23008": ["gpio_expander"],
    "mcp23016": ["gpio_expander"],
    "mcp23017": ["gpio_expander"],
    "mcp23s08": ["gpio_expander"],
    "mcp23s17": ["gpio_expander"],
    "mcp23x08_base": ["gpio_expander"],
    "mcp23x17_base": ["gpio_expander"],
    "mcp23xxx_base": ["gpio_expander"],
    "pca6416a": ["gpio_expander"],
    "pca9554": ["gpio_expander"],
    "pcf8574": ["gpio_expander"],
    "pi4ioe5v6408": ["gpio_expander"],
    "sn74hc165": ["gpio_expander"],
    "sn74hc595": ["gpio_expander"],
    "tca9548a": ["gpio_expander"],
    "tca9555": ["gpio_expander"],
    "weikai": ["uart"],
    "weikai_i2c": ["uart"],
    "weikai_spi": ["uart"],
    "wk2132_i2c": ["uart"],
    "wk2132_spi": ["uart"],
    "wk2168_i2c": ["uart"],
    "wk2168_spi": ["uart"],
    "wk2204_i2c": ["uart"],
    "wk2204_spi": ["uart"],
    "wk2212_i2c": ["uart"],
    "wk2212_spi": ["uart"],
    "xl9535": ["gpio_expander"],
    # NFC / RFID
    "pn532_i2c": ["nfc"],
    "pn532_spi": ["nfc"],
    "pn7150": ["nfc"],
    "pn7150_i2c": ["nfc"],
    "pn7160": ["nfc"],
    "pn7160_i2c": ["nfc"],
    "pn7160_spi": ["nfc"],
    "rc522_i2c": ["nfc"],
    # RTC chips
    "bm8563": ["time"],
    "ds1307": ["time"],
    "ds2484": ["one_wire"],
    "pcf85063": ["time"],
    "pcf8563": ["time"],
    "rx8130": ["time"],
    # Display infrastructure
    "lcd_menu": ["display"],
    # Audio / voice
    "media_source": ["media_player"],
    "micro_wake_word": ["audio"],
    # Improv (Wi-Fi provisioning protocol)
    "improv_base": ["network"],
    "improv_serial": ["network"],
    # Protocols / bridges
    "zigbee": ["zigbee"],
    "zwave_proxy": ["zwave"],
    # USB
    "tinyusb": ["usb"],
    "usb_cdc_acm": ["usb"],
    "usb_host": ["usb"],
    "usb_uart": ["usb"],
    # Radio / RF (remote control)
    "remote_transmitter": ["rf"],
    # CAN bus controllers
    "mcp2515": ["canbus"],
    # Platform-specific peripherals
    "rp2040_pio": ["platform"],
    # LED drivers
    "sm10bit_base": ["output"],
    "tm1651": ["display"],
    # Media / audio devices
    "dfplayer": ["media_player"],
    # Light control
    "lightwaverf": ["light"],
    # Motor drivers
    "grove_tb6612fng": ["stepper"],
    # BLE-based scanner devices
    "airthings_ble": ["bluetooth"],
    "exposure_notifications": ["bluetooth"],
    "mopeka_ble": ["bluetooth"],
    "radon_eye_ble": ["bluetooth"],
    "ruuvi_ble": ["bluetooth"],
    "xiaomi_ble": ["bluetooth"],
}


def _init_import_types(comp_dir: Path) -> set[str]:
    """Scan __init__.py for component-type imports.

    Detects two forms:
    - 'from esphome.components.light.effects import ...' → "light"
    - 'from esphome.components import sensor, binary_sensor' → "sensor", "binary_sensor"
    """
    init_py = comp_dir / "__init__.py"
    if not init_py.exists():
        return set()
    try:
        text = init_py.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return set()

    found: set[str] = set(_DOTPATH_IMPORT_RE.findall(text))

    for import_clause in _DIRECT_IMPORT_RE.findall(text):
        clause = import_clause[0] if isinstance(import_clause, tuple) else import_clause
        for token in re.split(r"[\s,()\\]+", clause):
            token = token.strip()
            if token in COMPONENT_TYPES:
                found.add(token)

    return found


def component_type(
    esphome_root: Path,
    component: str,
    docs_types: dict[str, list[str]] | None = None,
) -> list[str]:
    """Return type(s) for this component, mirroring esphome.io categories.

    Detection layers (first match wins for infrastructure, then entity detection):
    - Layer 0: self-identification — component IS a known entity type (sensor, switch…)
    - Layer 1: taxonomy — exclusive authority for bus/infra/platform components;
                          if matched, entity-type detection (layers 2-4) is skipped
                          entirely, preventing platform sub-components from leaking
                          their entity types up to the parent platform
    - Layer 2: esphome.io docs tree — canonical user-facing category
    - Layer 3: file/dir name scan — only when layers 0-2 found nothing
    - Layer 4: __init__.py import scan — only when layers 0-3 found nothing
    """
    comp_dir = esphome_root / "esphome" / "components" / component
    found: set[str] = set()

    # Layer 0: self-identification — the component itself is a known entity type
    if component in COMPONENT_TYPES:
        found.add(component)

    if not found:
        # Layer 1: taxonomy — exclusive for infrastructure/bus/platform components.
        # Bus platforms (uart, i2c, ble_client…) have entity-type subdirs that are
        # platform sub-components, not the platform's own entity types. Returning
        # early here prevents those sub-component names from leaking into the parent.
        tax = COMPONENT_TAXONOMY.get(component)
        if tax:
            return sorted(tax)

        # Layer 2: esphome.io docs tree (canonical)
        if docs_types:
            found.update(docs_types.get(component, []))

        if not found:
            # Layer 3: file/dir names matching known types
            for child in comp_dir.iterdir():
                name = child.stem if child.is_file() and child.suffix == ".py" else child.name
                if name in COMPONENT_TYPES:
                    found.add(name)

        if not found:
            # Layer 4: __init__.py import scan
            found.update(_init_import_types(comp_dir))

    return sorted(found) if found else [component]


KNOWN_PLATFORMS = frozenset({
    "esp32", "esp8266", "rp2040", "libretiny", "host",
    "zephyr", "bk72xx", "rtl87xx", "nrf52", "ln882x",
})

_IFDEF_RE = re.compile(r"#\s*ifdef\s+(USE_\w+)")
_PLATFORM_SUFFIX = {f"USE_{p.upper()}": p for p in KNOWN_PLATFORMS}

# Python validator patterns in __init__.py
# cv.only_on_esp32, cv.only_on_rp2040, etc. (attribute or called-as-function)
_ONLY_ON_ATTR_RE = re.compile(
    r"cv\.only_on_(" + "|".join(sorted(KNOWN_PLATFORMS)) + r")\b"
)
# cv.only_on([Platform.ESP32, PLATFORM_ESP8266, "esp32", ...]) and cv.only_on(PLATFORM_X)
_ONLY_ON_CALL_RE = re.compile(r"cv\.only_on\(([^)]+)\)")
# Tokens inside cv.only_on(...): Platform.ESP32, PLATFORM_ESP32, "esp32", 'esp32'
_PLAT_TOKEN_RE = re.compile(r'Platform\.(\w+)|PLATFORM_(\w+)|["\'](\w+)["\']', re.IGNORECASE)
# cv.only_with_framework(Framework.ZEPHYR / "zephyr")
_ONLY_ZEPHYR_RE = re.compile(r'cv\.only_with_framework\([^)]*zephyr[^)]*\)', re.IGNORECASE)
# DEPENDENCIES list — platform names embedded as strings
_DEPENDENCIES_RE = re.compile(r'DEPENDENCIES\s*=\s*\[([^\]]+)\]')

_TOP_LINES = 5


def _python_platforms(comp_dir: Path) -> set[str]:
    """Extract platform restrictions from __init__.py validators and DEPENDENCIES."""
    init_py = comp_dir / "__init__.py"
    if not init_py.exists():
        return set()
    try:
        text = init_py.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return set()

    found: set[str] = set()

    # cv.only_on_esp32, cv.only_on_rp2040, …
    for m in _ONLY_ON_ATTR_RE.finditer(text):
        found.add(m.group(1))

    # cv.only_on([Platform.ESP32, PLATFORM_BK72XX, "host", …]) / cv.only_on(PLATFORM_X)
    for call_m in _ONLY_ON_CALL_RE.finditer(text):
        for tok_m in _PLAT_TOKEN_RE.finditer(call_m.group(1)):
            raw = (tok_m.group(1) or tok_m.group(2) or tok_m.group(3)).lower()
            if raw in KNOWN_PLATFORMS:
                found.add(raw)

    # cv.only_with_framework(Framework.ZEPHYR / "zephyr")
    if _ONLY_ZEPHYR_RE.search(text):
        found.add("zephyr")

    # DEPENDENCIES = ["esp32", …] — platform name in dependency list
    for dep_m in _DEPENDENCIES_RE.finditer(text):
        for tok_m in re.finditer(r'["\'](\w+)["\']', dep_m.group(1)):
            raw = tok_m.group(1).lower()
            if raw in KNOWN_PLATFORMS:
                found.add(raw)

    return found


def platform_info(esphome_root: Path, component: str) -> dict:
    """Return supported_platforms for a component.

    Combines two sources:
    - C++ .h/.cpp files: USE_<PLATFORM> #ifdef in the first 5 lines
    - __init__.py: cv.only_on_*, cv.only_on([...]), cv.only_with_framework(zephyr),
                   DEPENDENCIES containing platform names
    supported_platforms: ["all"] if no restrictions found, else the restricted set.
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

    positive.update(_python_platforms(comp_dir))

    return {"supported_platforms": sorted(positive)}


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
