import tempfile
import unittest
from pathlib import Path

import core.telemetry_catalog as catalog_module
from core.telemetry_catalog import TelemetryVariableCatalog


class TelemetryVariableCatalogTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._real_path = catalog_module.OVERRIDES_PATH
        catalog_module.OVERRIDES_PATH = Path(self._tmpdir.name) / "telemetry_variable_overrides.json"

    def tearDown(self):
        catalog_module.OVERRIDES_PATH = self._real_path
        self._tmpdir.cleanup()

    def test_observe_discovers_new_keys(self):
        catalog = TelemetryVariableCatalog()
        catalog.observe({"esc_temp": 42.0})
        keys = [v.key for v in catalog.variables()]
        self.assertEqual(keys, ["esc_temp"])

    def test_observe_updates_last_value_for_an_existing_key(self):
        catalog = TelemetryVariableCatalog()
        catalog.observe({"esc_temp": 42.0})
        catalog.observe({"esc_temp": 45.5})
        variable = catalog.variables()[0]
        self.assertEqual(variable.last_value, 45.5)

    def test_empty_observe_is_a_no_op(self):
        catalog = TelemetryVariableCatalog()
        catalog.observe({})
        self.assertEqual(catalog.variables(), [])

    def test_variables_sorted_by_key(self):
        catalog = TelemetryVariableCatalog()
        catalog.observe({"zeta": 1.0, "alpha": 2.0, "mid": 3.0})
        keys = [v.key for v in catalog.variables()]
        self.assertEqual(keys, ["alpha", "mid", "zeta"])

    def test_label_falls_back_to_key_without_a_display_name(self):
        catalog = TelemetryVariableCatalog()
        catalog.observe({"esc_temp": 42.0})
        self.assertEqual(catalog.variables()[0].label, "esc_temp")

    def test_set_display_name_changes_the_label(self):
        catalog = TelemetryVariableCatalog()
        catalog.observe({"esc_temp": 42.0})
        catalog.set_display_name("esc_temp", "ESC-Temperatur")
        self.assertEqual(catalog.variables()[0].label, "ESC-Temperatur")

    def test_set_display_name_on_unknown_key_is_a_no_op(self):
        catalog = TelemetryVariableCatalog()
        catalog.set_display_name("never_seen", "Whatever")
        self.assertEqual(catalog.variables(), [])

    def test_hidden_variable_excluded_by_default(self):
        catalog = TelemetryVariableCatalog()
        catalog.observe({"esc_temp": 42.0})
        catalog.set_hidden("esc_temp", True)
        self.assertEqual(catalog.variables(), [])
        self.assertEqual(len(catalog.variables(include_hidden=True)), 1)

    def test_unhide_restores_visibility(self):
        catalog = TelemetryVariableCatalog()
        catalog.observe({"esc_temp": 42.0})
        catalog.set_hidden("esc_temp", True)
        catalog.set_hidden("esc_temp", False)
        self.assertEqual(len(catalog.variables()), 1)

    def test_clear_removes_discovered_variables(self):
        catalog = TelemetryVariableCatalog()
        catalog.observe({"esc_temp": 42.0})
        catalog.clear()
        self.assertEqual(catalog.variables(include_hidden=True), [])

    def test_display_name_and_hidden_overrides_persist_across_instances(self):
        first = TelemetryVariableCatalog()
        first.observe({"esc_temp": 42.0, "vtx_temp": 55.0})
        first.set_display_name("esc_temp", "ESC-Temperatur")
        first.set_hidden("vtx_temp", True)

        # A brand new catalog (e.g. app restart) with nothing observed yet
        # must still apply the persisted overrides once the same keys are
        # seen again.
        second = TelemetryVariableCatalog()
        second.observe({"esc_temp": 42.0, "vtx_temp": 55.0})
        by_key = {v.key: v for v in second.variables(include_hidden=True)}
        self.assertEqual(by_key["esc_temp"].display_name, "ESC-Temperatur")
        self.assertTrue(by_key["vtx_temp"].hidden)

    def test_clearing_a_display_name_removes_the_persisted_override(self):
        first = TelemetryVariableCatalog()
        first.observe({"esc_temp": 42.0})
        first.set_display_name("esc_temp", "ESC-Temperatur")
        first.set_display_name("esc_temp", "")

        second = TelemetryVariableCatalog()
        second.observe({"esc_temp": 42.0})
        self.assertEqual(second.variables()[0].label, "esc_temp")

    def test_missing_overrides_file_starts_clean(self):
        catalog = TelemetryVariableCatalog()
        self.assertEqual(catalog.variables(), [])

    def test_corrupt_overrides_file_falls_back_to_clean_state(self):
        catalog_module.OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
        catalog_module.OVERRIDES_PATH.write_text("not valid json{{{", encoding="utf-8")
        catalog = TelemetryVariableCatalog()
        catalog.observe({"esc_temp": 42.0})
        self.assertEqual(catalog.variables()[0].label, "esc_temp")


if __name__ == "__main__":
    unittest.main()
