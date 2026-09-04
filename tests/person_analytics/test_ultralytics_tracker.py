import unittest
import numpy as np

from pc.person_analytics.tracking import Detection, UltralyticsTracker


class UltralyticsTrackerTests(unittest.TestCase):
    def test_official_tracker_recovers_id_after_short_miss(self):
        tracker = UltralyticsTracker(track_buffer=30, frame_rate=20)
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        ids = []
        for frame in range(3):
            tracks = tracker.update([Detection((100 + frame, 100, 180 + frame, 300), .8)], frame * .05, image)
            ids.append(tracks[0].track_id)
        self.assertEqual(ids, [1, 1, 1])
        self.assertEqual(tracker.update([], .15, image), [])
        recovered = tracker.update([Detection((103, 100, 183, 300), .8)], .2, image)
        self.assertEqual([t.track_id for t in recovered], [1])


if __name__ == '__main__':
    unittest.main()
