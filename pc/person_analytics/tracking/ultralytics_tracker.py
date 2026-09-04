from __future__ import annotations

from types import SimpleNamespace


class UltralyticsTracker:
    """Adapter around Ultralytics' maintained BYTETracker/BOTSORT implementation."""

    def __init__(self, tracker_type="bytetrack", track_buffer=30, frame_rate=20.0,
                 high_thresh=0.25, low_thresh=0.1, new_track_thresh=0.25,
                 match_thresh=0.8, fuse_score=True):
        import numpy as np
        from ultralytics.trackers import BYTETracker, BOTSORT

        self.tracker_type = tracker_type.lower()
        if self.tracker_type not in {"bytetrack", "botsort"}:
            raise ValueError(f"unsupported Ultralytics tracker: {tracker_type}")
        # track_buffer is explicitly in frames. frame_rate is exposed so callers
        # can calculate it from a real configured stream rather than track_buffer/10.
        self.frame_rate = float(frame_rate)
        args = SimpleNamespace(
            tracker_type=self.tracker_type,
            track_high_thresh=float(high_thresh),
            track_low_thresh=float(low_thresh),
            new_track_thresh=float(new_track_thresh),
            track_buffer=int(track_buffer),
            match_thresh=float(match_thresh),
            fuse_score=bool(fuse_score),
            gmc_method="none",
            proximity_thresh=0.5,
            appearance_thresh=0.8,
            with_reid=False,
            model="",
        )
        self.args = args
        self.backend = (BOTSORT if self.tracker_type == "botsort" else BYTETracker)(args)
        self.tracks = {}
        self.np = np
        self.seen_ids = set()
        self.new_track_times = []
        self.track_recoveries = 0

    def update(self, detections, timestamp, image=None):
        import torch
        from .tracker import TrackState
        from ultralytics.engine.results import Boxes

        rows = [[*d.bbox, float(d.confidence), float(d.class_id)] for d in detections if d.class_id == 0]
        if rows:
            data = torch.tensor(rows, dtype=torch.float32)
            # xyxy, confidence, class
            boxes = Boxes(data, image.shape[:2] if image is not None else (1, 1))
        else:
            data = torch.zeros((0, 6), dtype=torch.float32)
            boxes = Boxes(data, image.shape[:2] if image is not None else (1, 1))
        output = self.backend.update(boxes, img=image)
        now_active = set()
        result = []
        for row in output:
            x1, y1, x2, y2, track_id, score, cls_id, _ = map(float, row[:8])
            tid = int(track_id)
            now_active.add(tid)
            previous = self.tracks.get(tid)
            if previous and previous.state == "LOST":
                self.track_recoveries += 1
            if tid not in self.seen_ids:
                self.seen_ids.add(tid); self.new_track_times.append(timestamp)
            first_seen = previous.first_seen if previous else timestamp
            state = TrackState(tid, (x1, y1, x2, y2), first_seen, timestamp,
                               state="CONFIRMED", age=(previous.age + 1 if previous else 1),
                               hits=(previous.hits + 1 if previous else 1),
                               detection_confidence=float(score))
            self.tracks[tid] = state
            result.append(state)
        for tid, old in list(self.tracks.items()):
            if tid not in now_active:
                old.state = "LOST"
                if timestamp - old.last_seen > self.args.track_buffer / max(self.frame_rate, 1.0):
                    old.state = "REMOVED"
        self.new_track_times=[t for t in self.new_track_times if timestamp-t <= 60]
        return result

    @property
    def backend_name(self):
        return f"ultralytics.{self.tracker_type}"

    def diagnostics(self):
        confirmed=sum(1 for t in self.tracks.values() if t.state == "CONFIRMED")
        lost=sum(1 for t in self.tracks.values() if t.state == "LOST")
        return {'active_tracks':confirmed,'confirmed_tracks':confirmed,'lost_tracks':lost,'new_tracks_last_minute':len(self.new_track_times),'track_recoveries':self.track_recoveries,'tracker_churn_high':len(self.new_track_times)>30}
