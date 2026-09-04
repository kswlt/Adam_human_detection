import unittest
from unittest.mock import Mock

from pc.person_analytics.capture import FramePacket, LatestFrameSink
from pc.person_analytics.capture.gateway_source import GatewayFrameSource
from pc.person_analytics.detection.person_detector import PersonDetector
from pc.person_analytics.tracking import Detection


class FrameSourceTests(unittest.TestCase):
    def packet(self, frame_id):
        return FramePacket(b"jpeg", frame_id, frame_id, 1.0, frame_id,
                           1920, 1080)

    def test_bounded_sink_drops_old_frames_and_keeps_latest(self):
        sink = LatestFrameSink(maxsize=2)
        for frame_id in range(1, 5):
            sink.publish(self.packet(frame_id))
        self.assertEqual([sink.get().frame_id, sink.get().frame_id], [3, 4])
        self.assertEqual(sink.stats()["dropped"], 2)

    def test_packet_is_immutable(self):
        packet = self.packet(1)
        with self.assertRaises(AttributeError):
            packet.frame_id = 2

    def test_gateway_stats_report_waiting_input_before_first_frame(self):
        source = GatewayFrameSource('http://127.0.0.1:1', timeout=.1)
        stats = source.stats()
        self.assertFalse(stats['healthy'])
        self.assertIsNone(stats['age_seconds'])

    def test_adaptive_detector_merges_second_pass_and_rate_limits_it(self):
        detector = PersonDetector(adaptive={
            'enabled': True, 'trigger_person_count': 1,
            'secondary_confidence': .15, 'secondary_inference_size': 960,
            'min_interval_seconds': 60,
        })
        detector._predict = Mock(side_effect=[
            [Detection((0, 0, 10, 10), .40)],
            [Detection((0, 0, 10, 10), .80), Detection((20, 0, 30, 10), .16)],
            [Detection((0, 0, 10, 10), .40)],
        ])
        merged = detector.detect(object())
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0].confidence, .80)
        self.assertTrue(detector.last_diagnostics['secondary_ran'])
        detector.detect(object())
        self.assertEqual(detector._predict.call_count, 3)
        self.assertFalse(detector.last_diagnostics['secondary_ran'])


if __name__ == "__main__":
    unittest.main()
