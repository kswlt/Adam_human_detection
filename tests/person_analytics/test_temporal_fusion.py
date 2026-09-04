import unittest
from pc.person_analytics.detection import TemporalDetectionFusion
from pc.person_analytics.tracking import Detection


class TemporalFusionTests(unittest.TestCase):
    def test_repeated_weak_detection_is_promoted(self):
        fusion = TemporalDetectionFusion(history_size=3, confirmation_hits=2)
        box = (10, 10, 50, 100)
        first = fusion.update([Detection(box, .20)], 0.0)
        second = fusion.update([Detection((11, 10, 51, 100), .20)], .25)
        self.assertEqual(fusion.last_raw_count, 1)
        self.assertEqual(fusion.last_fused_count, 1)
        self.assertLess(first[0].confidence, .45)
        self.assertGreaterEqual(second[0].confidence, .45)

    def test_single_frame_miss_does_not_create_fused_box(self):
        fusion = TemporalDetectionFusion()
        fusion.update([Detection((0, 0, 20, 40), .8)], 0.0)
        fused = fusion.update([], .25)
        self.assertEqual(fused, [])
        self.assertEqual(fusion.last_raw_count, 0)


if __name__ == '__main__':
    unittest.main()
