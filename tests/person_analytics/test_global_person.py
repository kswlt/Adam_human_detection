import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from pc.person_analytics.identity import GlobalPersonManager


class GlobalPersonTests(unittest.TestCase):
    def test_track_change_keeps_face_confirmed_global_id(self):
        manager = GlobalPersonManager(day="20260904")
        first = manager.update(7, 0.0, SimpleNamespace(person_id="P001", name="张三", confidence=.9))
        second = manager.update(12, 10.0, SimpleNamespace(person_id="P001", name="张三", confidence=.9))
        self.assertEqual(first.global_person_id, second.global_person_id)
        self.assertEqual(second.track_ids, [7, 12])
        self.assertEqual(manager.diagnostics()["track_recoveries"], 1)

    def test_unknown_is_a_valid_stable_identity(self):
        manager = GlobalPersonManager(day="20260904")
        person = manager.update(3, 1.0)
        self.assertTrue(person.global_person_id.startswith("DAY_20260904_"))
        self.assertEqual(person.name, "Unknown")

    def test_same_day_state_restores(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "global.json"
            manager = GlobalPersonManager(day="20260904")
            manager.update(3, 1.0, SimpleNamespace(person_id="P001", name="张三", confidence=.9))
            manager.save(path)
            restored = GlobalPersonManager(day="20260904")
            self.assertTrue(restored.load(path))
            self.assertEqual(restored.people["DAY_20260904_0001"].known_person_id, "P001")
