from collections import deque
from dataclasses import dataclass
import math

from ..tracking import Detection


def _iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1, ix2, iy2 = max(ax1, bx1), max(ay1, by1), min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    aa = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    bb = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    return inter / max(aa + bb - inter, 1e-6)


def _center_distance(a, b):
    ac = ((a[0] + a[2]) / 2, (a[1] + a[3]) / 2)
    bc = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
    scale = max(math.hypot(a[2] - a[0], a[3] - a[1]), 1.0)
    return math.hypot(ac[0] - bc[0], ac[1] - bc[1]) / scale


@dataclass
class _Evidence:
    bbox: tuple
    hits: int = 0
    last_seen: float = 0.0
    confidence: float = 0.0


class TemporalDetectionFusion:
    """Short detector evidence memory; it never invents a new person by itself."""
    def __init__(self, history_size=5, match_iou=.20, max_center_distance=1.2,
                 confirmation_hits=2, max_age_seconds=1.25):
        self.history = deque(maxlen=int(history_size))
        self.match_iou = float(match_iou)
        self.max_center_distance = float(max_center_distance)
        self.confirmation_hits = int(confirmation_hits)
        self.max_age_seconds = float(max_age_seconds)
        self.last_raw_count = 0
        self.last_fused_count = 0
        self.last_confirmed_low_count = 0

    def update(self, detections, timestamp):
        detections = [d for d in detections if d.class_id == 0]
        self.last_raw_count = len(detections)
        previous = [d for frame in self.history for d in frame]
        fused = []
        low_confirmed = 0
        for detection in detections:
            evidence = 1
            for old in previous:
                if _iou(detection.bbox, old.bbox) >= self.match_iou or _center_distance(detection.bbox, old.bbox) <= self.max_center_distance:
                    evidence += 1
                    break
            confidence = detection.confidence
            # A weak detection is promoted only after temporal evidence. This
            # allows it to continue an existing track while preserving the
            # tracker's separate new-track gate.
            if confidence < .45 and evidence >= self.confirmation_hits:
                confidence = max(confidence, .46)
                low_confirmed += 1
            fused.append(Detection(detection.bbox, confidence, detection.class_id))
        self.history.append(list(detections))
        self.last_fused_count = len(fused)
        self.last_confirmed_low_count = low_confirmed
        return fused
