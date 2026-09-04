import unittest
from pc.person_analytics.reid.gallery import DailyAppearanceGallery


class GalleryTests(unittest.TestCase):
    def test_ambiguous_candidates_are_rejected(self):
        gallery = DailyAppearanceGallery(threshold=.7, margin=.1)
        gallery.add("A", [1.0, 0.0]); gallery.add("B", [.99, .1])
        result = gallery.match([1.0, .05])
        self.assertEqual(result["status"], "AMBIGUOUS")
        self.assertIsNone(result["global_person_id"])
