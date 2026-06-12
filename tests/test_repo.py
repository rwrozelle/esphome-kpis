"""Tests for local repo inspection helpers."""

from esphome_kpis.repo import (
    codeowners_info,
    component_tests,
    component_type,
    date_to_version,
    platform_info,
)

RELEASES = [
    {"tag": "2024.1.0", "date": "2024-01-17"},
    {"tag": "2024.2.0", "date": "2024-02-14"},
    {"tag": "2024.3.0", "date": "2024-03-13"},
    {"tag": "2025.1.0", "date": "2025-01-15"},
]


class TestDateToVersion:
    def test_exact_release_date(self):
        assert date_to_version("2024-01-17", RELEASES) == "2024.1.0"

    def test_date_between_releases(self):
        assert date_to_version("2024-01-20", RELEASES) == "2024.2.0"

    def test_date_before_all_releases(self):
        assert date_to_version("2023-12-01", RELEASES) == "2024.1.0"

    def test_date_after_all_releases(self):
        assert date_to_version("2026-01-01", RELEASES) == "2025.1.0"

    def test_none_date(self):
        assert date_to_version(None, RELEASES) is None

    def test_empty_releases(self):
        assert date_to_version("2024-01-01", []) is None


class TestCodeownersInfo:
    def test_component_with_owners(self, tmp_path):
        codeowners = tmp_path / "CODEOWNERS"
        codeowners.parent.mkdir(parents=True, exist_ok=True)
        codeowners.write_text(
            "esphome/components/wifi @user1 @user2\n"
            "esphome/components/mqtt @user3\n"
        )
        result = codeowners_info(tmp_path, "wifi")
        assert result["has_codeowners"] is True
        assert result["codeowners_count"] == 2
        assert result["codeowners"] == ["@user1", "@user2"]

    def test_component_not_in_codeowners(self, tmp_path):
        codeowners = tmp_path / "CODEOWNERS"
        codeowners.parent.mkdir(parents=True, exist_ok=True)
        codeowners.write_text("esphome/components/wifi @user1\n")
        result = codeowners_info(tmp_path, "mqtt")
        assert result["has_codeowners"] is False
        assert result["codeowners_count"] == 0

    def test_no_codeowners_file(self, tmp_path):
        result = codeowners_info(tmp_path, "wifi")
        assert result["has_codeowners"] is False

    def test_skips_comments_and_blank_lines(self, tmp_path):
        codeowners = tmp_path / "CODEOWNERS"
        codeowners.parent.mkdir(parents=True, exist_ok=True)
        codeowners.write_text(
            "# This is a comment\n\nesphome/components/wifi @user1\n"
        )
        result = codeowners_info(tmp_path, "wifi")
        assert result["codeowners_count"] == 1


class TestComponentTests:
    def test_no_test_dir(self, tmp_path):
        (tmp_path / "tests" / "components").mkdir(parents=True)
        result = component_tests(tmp_path, "nonexistent")
        assert result == {"has_tests": False, "test_file_count": 0}

    def test_test_dir_with_yamls(self, tmp_path):
        test_dir = tmp_path / "tests" / "components" / "wifi"
        test_dir.mkdir(parents=True)
        (test_dir / "test.esp32-idf.yaml").write_text("")
        (test_dir / "test.esp8266-ard.yaml").write_text("")
        result = component_tests(tmp_path, "wifi")
        assert result["has_tests"] is True
        assert result["test_file_count"] == 2


class TestComponentType:
    # --- Layer 0+1: self-identification and file/dir scan ---

    def test_base_entity_type_self_identifies(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "sensor"
        comp_dir.mkdir(parents=True)
        assert component_type(tmp_path, "sensor") == ["sensor"]

    def test_detects_sensor_py(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "dht"
        comp_dir.mkdir(parents=True)
        (comp_dir / "sensor.py").write_text("")
        assert component_type(tmp_path, "dht") == ["sensor"]

    def test_detects_subdir(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "gpio"
        (comp_dir / "binary_sensor").mkdir(parents=True)
        (comp_dir / "switch").mkdir(parents=True)
        result = component_type(tmp_path, "gpio")
        assert result == ["binary_sensor", "switch"]

    def test_multi_type_component(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "combo"
        comp_dir.mkdir(parents=True)
        (comp_dir / "sensor.py").write_text("")
        (comp_dir / "text_sensor.py").write_text("")
        (comp_dir / "button").mkdir()
        result = component_type(tmp_path, "combo")
        assert result == ["button", "sensor", "text_sensor"]

    def test_detects_display_subdir(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "ili9xxx"
        (comp_dir / "display").mkdir(parents=True)
        assert component_type(tmp_path, "ili9xxx") == ["display"]

    def test_detects_touchscreen_subdir(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "axs15231"
        (comp_dir / "touchscreen").mkdir(parents=True)
        assert component_type(tmp_path, "axs15231") == ["touchscreen"]

    def test_no_double_count_dir_and_py(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "test_comp"
        comp_dir.mkdir(parents=True)
        (comp_dir / "sensor.py").write_text("")
        (comp_dir / "sensor").mkdir()
        result = component_type(tmp_path, "test_comp")
        assert result == ["sensor"]

    # --- Layer 1: esphome.io docs tree ---

    def test_docs_tree_used_as_layer1(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "wiegand"
        comp_dir.mkdir(parents=True)
        (comp_dir / "__init__.py").write_text("")
        docs = {"wiegand": ["binary_sensor"]}
        assert component_type(tmp_path, "wiegand", docs_types=docs) == ["binary_sensor"]

    def test_docs_tree_multi_category(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "gpio"
        comp_dir.mkdir(parents=True)
        docs = {"gpio": ["binary_sensor", "switch", "output"]}
        result = component_type(tmp_path, "gpio", docs_types=docs)
        assert result == ["binary_sensor", "output", "switch"]

    def test_docs_tree_overrides_file_scan(self, tmp_path):
        # docs say sensor, but component has a switch.py — docs win (layer 1 short-circuits layer 2)
        comp_dir = tmp_path / "esphome" / "components" / "my_comp"
        comp_dir.mkdir(parents=True)
        (comp_dir / "switch.py").write_text("")
        docs = {"my_comp": ["sensor"]}
        result = component_type(tmp_path, "my_comp", docs_types=docs)
        assert result == ["sensor"]
        assert "switch" not in result

    def test_taxonomy_exclusive_skips_docs(self, tmp_path):
        # uart is in taxonomy — docs are ignored even when docs_types is populated
        comp_dir = tmp_path / "esphome" / "components" / "uart"
        (comp_dir / "button").mkdir(parents=True)
        docs = {"uart": ["button", "event", "switch"]}
        result = component_type(tmp_path, "uart", docs_types=docs)
        assert result == ["uart"]
        assert "button" not in result

    def test_docs_tree_none_falls_through_to_file_scan(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "dht"
        comp_dir.mkdir(parents=True)
        (comp_dir / "sensor.py").write_text("")
        # No docs_types → layer 2 runs
        assert component_type(tmp_path, "dht", docs_types=None) == ["sensor"]

    # --- Layer 2: __init__.py import scan ---

    def test_import_scan_detects_light_effect(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "adalight"
        comp_dir.mkdir(parents=True)
        (comp_dir / "__init__.py").write_text(
            "from esphome.components.light.effects import register_addressable_effect\n"
        )
        assert component_type(tmp_path, "adalight") == ["light"]

    def test_import_scan_detects_direct_import(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "my_sensor"
        comp_dir.mkdir(parents=True)
        (comp_dir / "__init__.py").write_text(
            "from esphome.components import sensor\n"
        )
        assert component_type(tmp_path, "my_sensor") == ["sensor"]

    def test_import_scan_skipped_when_layer1_finds_type(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "my_comp"
        comp_dir.mkdir(parents=True)
        (comp_dir / "switch.py").write_text("")
        # import says sensor but file scan says switch — file scan wins
        (comp_dir / "__init__.py").write_text(
            "from esphome.components import sensor\n"
        )
        assert component_type(tmp_path, "my_comp") == ["switch"]

    def test_import_scan_ignores_non_type_imports(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "my_helper"
        comp_dir.mkdir(parents=True)
        (comp_dir / "__init__.py").write_text(
            "from esphome.components import esp32\n"
            "import esphome.config_validation as cv\n"
        )
        # esp32 is not in COMPONENT_TYPES; my_helper not in taxonomy → falls back to name
        assert component_type(tmp_path, "my_helper") == ["my_helper"]

    # --- Layer 3: taxonomy ---

    def test_taxonomy_platform(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "esp32"
        comp_dir.mkdir(parents=True)
        (comp_dir / "__init__.py").write_text("")
        assert component_type(tmp_path, "esp32") == ["platform"]

    def test_taxonomy_bus(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "i2c"
        comp_dir.mkdir(parents=True)
        (comp_dir / "__init__.py").write_text("")
        assert component_type(tmp_path, "i2c") == ["i2c"]

    def test_taxonomy_wifi(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "wifi"
        comp_dir.mkdir(parents=True)
        (comp_dir / "__init__.py").write_text("")
        assert component_type(tmp_path, "wifi") == ["wifi"]

    def test_taxonomy_display_infra(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "font"
        comp_dir.mkdir(parents=True)
        (comp_dir / "__init__.py").write_text("")
        assert component_type(tmp_path, "font") == ["display"]

    def test_taxonomy_exclusive_skips_subdir_scan(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "uart"
        (comp_dir / "button").mkdir(parents=True)
        (comp_dir / "switch").mkdir(parents=True)
        # uart is in taxonomy — entity-type subdirs are not counted as uart's own types
        result = component_type(tmp_path, "uart")
        assert result == ["uart"]
        assert "button" not in result
        assert "switch" not in result

    def test_unknown_component_falls_back_to_name(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "custom_helper"
        comp_dir.mkdir(parents=True)
        (comp_dir / "__init__.py").write_text("# utility\n")
        assert component_type(tmp_path, "custom_helper") == ["custom_helper"]


class TestPlatformInfo:
    def test_no_guards_means_all(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "dht"
        comp_dir.mkdir(parents=True)
        (comp_dir / "dht.h").write_text("// generic component\n")
        (comp_dir / "dht.cpp").write_text("// no platform guards\n")
        assert platform_info(tmp_path, "dht") == {"supported_platforms": []}

    def test_ifdef_at_top_of_header(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "adc"
        comp_dir.mkdir(parents=True)
        (comp_dir / "adc_esp32.h").write_text("#ifdef USE_ESP32\nstruct Esp32Adc {};\n#endif\n")
        (comp_dir / "adc_rp2040.h").write_text("#ifdef USE_RP2040\nstruct Rp2040Adc {};\n#endif\n")
        assert platform_info(tmp_path, "adc") == {"supported_platforms": ["esp32", "rp2040"]}

    def test_ifdef_at_top_of_cpp(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "adc"
        comp_dir.mkdir(parents=True)
        (comp_dir / "adc_esp8266.cpp").write_text("#ifdef USE_ESP8266\nvoid foo() {}\n#endif\n")
        assert platform_info(tmp_path, "adc") == {"supported_platforms": ["esp8266"]}

    def test_mid_file_ifdef_ignored(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "dht"
        comp_dir.mkdir(parents=True)
        lines = ["#include <stdint.h>"] * 10 + ["#ifdef USE_ESP32", "void esp_thing();", "#endif"]
        (comp_dir / "dht.cpp").write_text("\n".join(lines))
        assert platform_info(tmp_path, "dht") == {"supported_platforms": []}

    def test_combined_header_and_cpp(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "adc"
        comp_dir.mkdir(parents=True)
        (comp_dir / "adc_esp32.h").write_text("#ifdef USE_ESP32\n#endif\n")
        (comp_dir / "adc_zephyr.h").write_text("#ifdef USE_ZEPHYR\n#endif\n")
        (comp_dir / "adc_esp8266.cpp").write_text("#ifdef USE_ESP8266\n#endif\n")
        (comp_dir / "adc_rp2040.cpp").write_text("#ifdef USE_RP2040\n#endif\n")
        assert platform_info(tmp_path, "adc") == {"supported_platforms": ["esp32", "esp8266", "rp2040", "zephyr"]}

    def test_txt_files_ignored(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "wifi"
        comp_dir.mkdir(parents=True)
        (comp_dir / "readme.txt").write_text("#ifdef USE_ESP8266\n")
        assert platform_info(tmp_path, "wifi") == {"supported_platforms": []}

    def test_python_only_on_attr(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "wifi"
        comp_dir.mkdir(parents=True)
        (comp_dir / "__init__.py").write_text("cv.only_on_esp32\n")
        assert platform_info(tmp_path, "wifi") == {"supported_platforms": ["esp32"]}

    def test_python_only_on_list_platform_enum(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "foo"
        comp_dir.mkdir(parents=True)
        (comp_dir / "__init__.py").write_text(
            "cv.only_on([Platform.ESP32, Platform.ESP8266])\n"
        )
        assert platform_info(tmp_path, "foo") == {"supported_platforms": ["esp32", "esp8266"]}

    def test_python_only_on_list_platform_const(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "foo"
        comp_dir.mkdir(parents=True)
        (comp_dir / "__init__.py").write_text(
            "cv.only_on([PLATFORM_ESP32, PLATFORM_BK72XX])\n"
        )
        assert platform_info(tmp_path, "foo") == {"supported_platforms": ["bk72xx", "esp32"]}

    def test_python_only_on_single_const(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "foo"
        comp_dir.mkdir(parents=True)
        (comp_dir / "__init__.py").write_text("cv.only_on(PLATFORM_HOST)\n")
        assert platform_info(tmp_path, "foo") == {"supported_platforms": ["host"]}

    def test_python_zephyr_framework(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "foo"
        comp_dir.mkdir(parents=True)
        (comp_dir / "__init__.py").write_text('cv.only_with_framework(Framework.ZEPHYR)\n')
        assert platform_info(tmp_path, "foo") == {"supported_platforms": ["zephyr"]}

    def test_python_dependencies_platform(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "foo"
        comp_dir.mkdir(parents=True)
        (comp_dir / "__init__.py").write_text('DEPENDENCIES = ["uart", "esp32"]\n')
        assert platform_info(tmp_path, "foo") == {"supported_platforms": ["esp32"]}

    def test_python_and_cpp_union(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "foo"
        comp_dir.mkdir(parents=True)
        (comp_dir / "__init__.py").write_text("cv.only_on_rp2040\n")
        (comp_dir / "foo_esp32.h").write_text("#ifdef USE_ESP32\n#endif\n")
        result = platform_info(tmp_path, "foo")
        assert set(result["supported_platforms"]) == {"esp32", "rp2040"}
