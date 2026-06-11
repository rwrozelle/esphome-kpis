"""Tests for local repo inspection helpers."""

from esphome_kpis.repo import (
    codeowners_info,
    component_tests,
    date_to_version,
    entity_types,
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
        codeowners = tmp_path / ".github" / "CODEOWNERS"
        codeowners.parent.mkdir(parents=True)
        codeowners.write_text(
            "esphome/components/wifi @user1 @user2\n"
            "esphome/components/mqtt @user3\n"
        )
        result = codeowners_info(tmp_path, "wifi")
        assert result["has_codeowners"] is True
        assert result["codeowners_count"] == 2
        assert result["codeowners"] == ["@user1", "@user2"]

    def test_component_not_in_codeowners(self, tmp_path):
        codeowners = tmp_path / ".github" / "CODEOWNERS"
        codeowners.parent.mkdir(parents=True)
        codeowners.write_text("esphome/components/wifi @user1\n")
        result = codeowners_info(tmp_path, "mqtt")
        assert result["has_codeowners"] is False
        assert result["codeowners_count"] == 0

    def test_no_codeowners_file(self, tmp_path):
        result = codeowners_info(tmp_path, "wifi")
        assert result["has_codeowners"] is False

    def test_skips_comments_and_blank_lines(self, tmp_path):
        codeowners = tmp_path / ".github" / "CODEOWNERS"
        codeowners.parent.mkdir(parents=True)
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


class TestEntityTypes:
    def test_detects_sensor_py(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "dht"
        comp_dir.mkdir(parents=True)
        (comp_dir / "sensor.py").write_text("")
        assert entity_types(tmp_path, "dht") == ["sensor"]

    def test_detects_subdir(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "gpio"
        (comp_dir / "binary_sensor").mkdir(parents=True)
        (comp_dir / "switch").mkdir(parents=True)
        result = entity_types(tmp_path, "gpio")
        assert result == ["binary_sensor", "switch"]

    def test_multi_type_component(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "combo"
        comp_dir.mkdir(parents=True)
        (comp_dir / "sensor.py").write_text("")
        (comp_dir / "text_sensor.py").write_text("")
        (comp_dir / "button").mkdir()
        result = entity_types(tmp_path, "combo")
        assert result == ["button", "sensor", "text_sensor"]

    def test_ignores_non_entity_files(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "wifi"
        comp_dir.mkdir(parents=True)
        (comp_dir / "wifi.cpp").write_text("")
        (comp_dir / "helpers").mkdir()
        assert entity_types(tmp_path, "wifi") == []

    def test_no_double_count_dir_and_py(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "test_comp"
        comp_dir.mkdir(parents=True)
        (comp_dir / "sensor.py").write_text("")
        (comp_dir / "sensor").mkdir()
        result = entity_types(tmp_path, "test_comp")
        assert result == ["sensor"]


class TestPlatformInfo:
    def test_no_guards_means_all(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "dht"
        comp_dir.mkdir(parents=True)
        (comp_dir / "dht.h").write_text("// generic component\n")
        (comp_dir / "dht.cpp").write_text("// no platform guards\n")
        assert platform_info(tmp_path, "dht") == {"supported_platforms": ["all"]}

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
        assert platform_info(tmp_path, "dht") == {"supported_platforms": ["all"]}

    def test_combined_header_and_cpp(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "adc"
        comp_dir.mkdir(parents=True)
        (comp_dir / "adc_esp32.h").write_text("#ifdef USE_ESP32\n#endif\n")
        (comp_dir / "adc_zephyr.h").write_text("#ifdef USE_ZEPHYR\n#endif\n")
        (comp_dir / "adc_esp8266.cpp").write_text("#ifdef USE_ESP8266\n#endif\n")
        (comp_dir / "adc_rp2040.cpp").write_text("#ifdef USE_RP2040\n#endif\n")
        assert platform_info(tmp_path, "adc") == {"supported_platforms": ["esp32", "esp8266", "rp2040", "zephyr"]}

    def test_ignores_non_cpp_h_files(self, tmp_path):
        comp_dir = tmp_path / "esphome" / "components" / "wifi"
        comp_dir.mkdir(parents=True)
        (comp_dir / "__init__.py").write_text("cv.only_on_esp32\n")
        (comp_dir / "readme.txt").write_text("#ifdef USE_ESP8266\n")
        assert platform_info(tmp_path, "wifi") == {"supported_platforms": ["all"]}
