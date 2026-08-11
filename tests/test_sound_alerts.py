import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import core.sound_alerts as sound_alerts_module
from core.sound_alerts import (
    WARNING_TYPES,
    get_sound_path,
    list_available_sounds,
    load_overrides,
    set_sound,
)


class ListAvailableSoundsTest(unittest.TestCase):
    def test_finds_real_bundled_edgetx_sounds(self):
        # assets/en/*.wav (+ SCRIPTS/, SYSTEM/ subfolders) ship with the repo -
        # a real (not mocked) scan should find several hundred files.
        sounds = list_available_sounds()
        self.assertGreater(len(sounds), 100)
        self.assertTrue(all(s.relative_path.endswith(".wav") for s in sounds))

    def test_sorted_by_display_name(self):
        sounds = list_available_sounds()
        names = [s.display_name.lower() for s in sounds]
        self.assertEqual(names, sorted(names))

    def test_missing_sounds_dir_returns_empty(self):
        with patch.object(sound_alerts_module, "resource_path", return_value=Path("/does/not/exist")):
            self.assertEqual(list_available_sounds(), [])


class OverridesPersistenceTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self._patcher = patch.object(
            sound_alerts_module, "OVERRIDES_PATH", Path(self._tmpdir.name) / "sound_alert_settings.json"
        )
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def test_no_file_yields_empty_overrides(self):
        self.assertEqual(load_overrides(), {})

    def test_set_sound_persists_and_round_trips(self):
        set_sound("tts_critical", "SYSTEM/crshof.wav")
        self.assertEqual(load_overrides(), {"tts_critical": "SYSTEM/crshof.wav"})

    def test_set_sound_none_clears_override(self):
        set_sound("tts_critical", "SYSTEM/crshof.wav")
        set_sound("tts_critical", None)
        self.assertEqual(load_overrides(), {})

    def test_unknown_key_is_ignored(self):
        set_sound("not_a_real_warning_key", "foo.wav")
        self.assertEqual(load_overrides(), {})

    def test_corrupt_file_yields_empty_overrides(self):
        sound_alerts_module.OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
        sound_alerts_module.OVERRIDES_PATH.write_text("{not valid json", encoding="utf-8")
        self.assertEqual(load_overrides(), {})

    def test_non_dict_json_yields_empty_overrides(self):
        sound_alerts_module.OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
        sound_alerts_module.OVERRIDES_PATH.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        self.assertEqual(load_overrides(), {})

    def test_multiple_keys_independent(self):
        set_sound("tts_critical", "a.wav")
        set_sound("tts_low", "b.wav")
        self.assertEqual(load_overrides(), {"tts_critical": "a.wav", "tts_low": "b.wav"})
        set_sound("tts_critical", None)
        self.assertEqual(load_overrides(), {"tts_low": "b.wav"})


class GetSoundPathTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self._patcher = patch.object(
            sound_alerts_module, "OVERRIDES_PATH", Path(self._tmpdir.name) / "sound_alert_settings.json"
        )
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def test_no_key_returns_none(self):
        self.assertIsNone(get_sound_path(None))
        self.assertIsNone(get_sound_path(""))

    def test_unconfigured_key_returns_none(self):
        self.assertIsNone(get_sound_path("tts_critical"))

    def test_configured_but_missing_file_returns_none(self):
        set_sound("tts_critical", "no/such/file.wav")
        self.assertIsNone(get_sound_path("tts_critical"))

    def test_configured_existing_file_resolves(self):
        # Use a real bundled sound so this test doesn't depend on a fake
        # resource_path() setup - SYSTEM/armed.wav ships with the repo.
        sounds = list_available_sounds()
        real = next((s for s in sounds if "armed" in s.relative_path.lower()), sounds[0])
        set_sound("tts_critical", real.relative_path)
        path = get_sound_path("tts_critical")
        self.assertIsNotNone(path)
        self.assertTrue(path.is_file())


class WarningTypesTest(unittest.TestCase):
    def test_covers_all_seven_known_tts_keys(self):
        keys = {w.key for w in WARNING_TYPES}
        self.assertEqual(
            keys,
            {
                "tts_low",
                "tts_critical",
                "tts_geofence_breach",
                "tts_nfz_proximity",
                "tts_energy_budget_low",
                "tts_energy_budget_critical",
                "tts_model_lost",
            },
        )

    def test_no_duplicate_label_keys(self):
        label_keys = [w.label_key for w in WARNING_TYPES]
        self.assertEqual(len(label_keys), len(set(label_keys)))


if __name__ == "__main__":
    unittest.main()
