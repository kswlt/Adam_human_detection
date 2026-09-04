"""Non-blocking HTTP adapter for the existing Gateway latest-frame endpoint."""
from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request

from .frame_source import FramePacket, LatestFrameSink


class GatewayFrameSource:
    """Poll Gateway in a producer thread and hand off only the newest frames."""

    def __init__(self, url: str, maxsize: int = 2, timeout: float = 2.0):
        self.url=url; self.timeout=timeout; self.sink=LatestFrameSink(maxsize); self.stop=threading.Event(); self.thread=None; self._frame_id=0

    def start(self):
        self.thread=threading.Thread(target=self._run,name='analytics-gateway-source',daemon=True); self.thread.start(); return self

    def _run(self):
        while not self.stop.is_set():
            try:
                with urllib.request.urlopen(self.url,timeout=self.timeout) as response: payload=response.read()
                if payload:
                    self._frame_id+=1
                    self.sink.publish(FramePacket(payload,self._frame_id,self._frame_id,time.monotonic(),time.time_ns(),0,0))
            except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,OSError):
                self.stop.wait(.1)

    def get(self,timeout=1.0): return self.sink.get(timeout)
    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(3)
    def stats(self): return self.sink.stats()
