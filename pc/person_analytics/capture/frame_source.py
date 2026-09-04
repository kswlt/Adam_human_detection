"""Bounded frame handoff from the existing gateway to analytics.

This module deliberately has no image/AI dependency. The gateway can publish
validated JPEG bytes here without waiting for an analytics consumer.
"""
from __future__ import annotations

from dataclasses import dataclass
import queue
import threading
from typing import Optional


@dataclass(frozen=True)
class FramePacket:
    """An immutable, already validated camera frame snapshot."""

    payload: bytes
    frame_id: int
    source_seq: int
    received_mono: float
    received_wall_ns: int
    width: int
    height: int


class LatestFrameSink:
    """A bounded handoff that always favors the newest frame."""

    def __init__(self, maxsize: int = 2):
        if maxsize < 1:
            raise ValueError("maxsize must be positive")
        self.queue: queue.Queue[FramePacket] = queue.Queue(maxsize=maxsize)
        self._lock = threading.Lock()
        self.dropped = 0
        self.published = 0

    def publish(self, packet: FramePacket) -> None:
        """Publish without blocking the camera/gateway worker."""
        while True:
            try:
                self.queue.put_nowait(packet)
                with self._lock:
                    self.published += 1
                return
            except queue.Full:
                try:
                    self.queue.get_nowait()
                except queue.Empty:
                    continue
                with self._lock:
                    self.dropped += 1

    def get(self, timeout: Optional[float] = None) -> FramePacket:
        return self.queue.get(timeout=timeout)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"published": self.published, "dropped": self.dropped,
                    "queue_size": self.queue.qsize()}
