import unittest

from pc.person_analytics.capture import FramePacket, LatestFrameSink


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


if __name__ == "__main__":
    unittest.main()

