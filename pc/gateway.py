"""Zenoh protocol input, native JPEG preview, and official Foxglove SDK output."""
import argparse
import asyncio
import hashlib
import io
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import queue
import struct
import threading
import time

from aiohttp import web
import foxglove
from foxglove import channels, messages as fg
from PIL import Image
import zenoh

from . import active_msgs_pb2 as pb
from .recorder import RawRecorder
from .person_analytics.capture import FramePacket

ROOT = Path(__file__).resolve().parents[1]
LOG = logging.getLogger("yunke")
POINT = struct.Struct("<dddIfIi")
NT = fg.PackedElementFieldNumericType
POINT_FIELDS = [
    fg.PackedElementField(name=name, offset=offset, type=kind)
    for name, offset, kind in [
        ("x", 0, NT.Float64), ("y", 8, NT.Float64), ("z", 16, NT.Float64),
        ("rgbi", 24, NT.Uint32), ("intensity", 28, NT.Float32),
        ("ring", 32, NT.Uint32), ("offset", 36, NT.Int32),
    ]
]


def zenoh_config(endpoint):
    cfg = zenoh.Config()
    cfg.insert_json5("mode", json.dumps("client"))
    cfg.insert_json5("connect/endpoints", json.dumps([endpoint]))
    cfg.insert_json5("connect/timeout_ms", "0")
    cfg.insert_json5("connect/exit_on_failure", "false")
    cfg.insert_json5("scouting/multicast/enabled", "false")
    return cfg


class Source:
    def __init__(self, kind, cfg, notify, recorder=None, frame_sink=None):
        self.kind, self.cfg, self.notify = kind, cfg, notify
        self.recorder = recorder
        self.frame_sink = frame_sink
        self.topic = f"active/{cfg['sn']}/{kind}"
        self.endpoint = cfg[f"{kind}_endpoint"]
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.pending = queue.Queue(maxsize=4)
        self.latest = None
        self.times = []
        self.last_rx = time.monotonic()
        self.stats = dict(received=0, forwarded=0, invalid=0, queue_dropped=0,
                          seq_gaps=0, seq_resets=0, timestamp_nonmono=0,
                          reconnects=0, last_seq=None, source_stamp_ns=None,
                          last_error=None, last_processed_mono=None, stale_events=0,
                          process_max_ms=0, sdk_log_max_ms=0, queue_delay_max_ms=0)
        channel_type = channels.CompressedImageChannel if kind == "image" else channels.PointCloudChannel
        self.channel = channel_type(self.topic, metadata={
            "source": "Zenoh", "source_endpoint": self.endpoint,
            "source_type": "active_msgs.ImageMsgArray" if kind == "image" else "active_msgs.LidarPointMsgArray",
            "display_clock": "PC receive wall clock; original stamps retained in /api/status",
        })
        self.thread = threading.Thread(target=self.run, name=f"zenoh-{kind}", daemon=True)

    def receive(self, sample):
        item = (sample.payload.to_bytes(), time.monotonic(), time.time_ns())
        with self.lock:
            self.stats["received"] += 1
            self.last_rx = item[1]
        try:
            self.pending.put_nowait(item)
        except queue.Full:
            try:
                self.pending.get_nowait()
                with self.lock:
                    self.stats["queue_dropped"] += 1
            except queue.Empty:
                pass
            try:
                self.pending.put_nowait(item)
            except queue.Full:
                with self.lock:
                    self.stats["queue_dropped"] += 1

    def process(self, item):
        payload, received_mono, wall_ns = item
        started = time.monotonic()
        arr = pb.ImageMsgArray() if self.kind == "image" else pb.LidarPointMsgArray()
        arr.ParseFromString(payload)
        if len(arr.array) != 1:
            raise ValueError(f"array length {len(arr.array)} (expected 1)")
        msg = arr.array[0]
        if not msg.HasField("header"):
            raise ValueError("missing Header")
        timestamp = fg.Timestamp(sec=wall_ns // 1_000_000_000, nsec=wall_ns % 1_000_000_000)
        extra = {}
        if self.kind == "image":
            jpeg = msg.data
            if msg.format != pb.ImageFormatJpeg or jpeg[:2] != b"\xff\xd8" or jpeg[-2:] != b"\xff\xd9":
                raise ValueError("not a complete protocol JPEG")
            with Image.open(io.BytesIO(jpeg)) as im:
                if im.format != "JPEG" or im.size != (msg.width, msg.height):
                    raise ValueError("JPEG dimensions do not match ImageMsg")
            display = fg.CompressedImage(timestamp=timestamp, frame_id="camera", data=jpeg, format="jpeg")
            extra = dict(width=msg.width, height=msg.height, jpeg_bytes=len(jpeg),
                         sha256=hashlib.sha256(jpeg).hexdigest())
        else:
            if msg.header.scaler != 1000:
                raise ValueError(f"pointcloud scaler={msg.header.scaler}, expected 1000")
            data = bytearray(POINT.size * len(msg.points))
            for index, p in enumerate(msg.points):
                POINT.pack_into(data, index * POINT.size, p.x / 1000, p.y / 1000, p.z / 1000,
                                p.rgbi, float(p.rgbi & 255), p.ring, p.offset)
            display = fg.PointCloud(timestamp=timestamp, frame_id="lidar",
                                    pose=fg.Pose(orientation=fg.Quaternion(w=1)),
                                    point_stride=POINT.size, fields=POINT_FIELDS, data=bytes(data))
            extra = dict(points=len(msg.points), displayed_points=len(data) // POINT.size)
            if self.recorder:
                self.recorder.submit(msg.header.stamp, payload)
        # SDK serialization and I/O run outside the Zenoh receive callback.
        log_started = time.monotonic()
        self.channel.log(display, log_time=wall_ns)
        finished = time.monotonic()
        with self.lock:
            self.stats["process_max_ms"] = max(self.stats["process_max_ms"], (finished-started)*1000)
            self.stats["sdk_log_max_ms"] = max(self.stats["sdk_log_max_ms"], (finished-log_started)*1000)
            self.stats["queue_delay_max_ms"] = max(self.stats["queue_delay_max_ms"], (started-received_mono)*1000)
            prev, stamp = self.stats["last_seq"], self.stats["source_stamp_ns"]
            if prev is not None:
                delta = (msg.header.seq - prev) & 0xffffffff
                if 1 < delta < 0x80000000:
                    self.stats["seq_gaps"] += delta - 1
                elif delta == 0 or delta >= 0x80000000:
                    self.stats["seq_resets"] += 1
                if msg.header.stamp <= stamp:
                    self.stats["timestamp_nonmono"] += 1
            self.stats.update(last_seq=msg.header.seq, source_stamp_ns=msg.header.stamp,
                              last_processed_mono=received_mono, last_error=None, **extra)
            self.stats["forwarded"] += 1
            self.times.append(received_mono)
            self.times = [t for t in self.times if t >= received_mono - 5]
            self.latest = dict(payload=payload, data=msg.data if self.kind == "image" else None,
                               frame_id=self.stats["forwarded"], seq=msg.header.seq,
                               received_mono=received_mono, wall_ns=wall_ns, **extra)
            frame_packet = None
            if self.kind == "image" and self.frame_sink is not None:
                frame_packet = FramePacket(
                    payload=bytes(msg.data), frame_id=self.stats["forwarded"],
                    source_seq=msg.header.seq, received_mono=received_mono,
                    received_wall_ns=wall_ns, width=msg.width, height=msg.height)
        if frame_packet is not None:
            try:
                self.frame_sink.publish(frame_packet)
            except Exception:
                # Analytics is optional and must never take down the gateway.
                LOG.exception("analytics frame sink failed")
        self.notify()

    def status(self):
        with self.lock:
            stats = dict(self.stats)
            now = time.monotonic()
            age = None if self.latest is None else now - self.latest["received_mono"]
            times = [t for t in self.times if t >= now - 5]
            hz = (len(times) - 1) / (times[-1] - times[0]) if len(times) > 1 else 0.0
        stats.update(topic=self.topic, endpoint=self.endpoint, age_seconds=age,
                     hz=hz, healthy=age is not None and age < self.cfg["stale_seconds"])
        return stats

    def run(self):
        while not self.stop.is_set():
            session = None
            try:
                session = zenoh.open(zenoh_config(self.endpoint))
                subscriber = session.declare_subscriber(self.topic, self.receive)
                with self.lock:
                    self.last_rx = time.monotonic()
                LOG.info("subscribed %s at %s", self.topic, self.endpoint)
                stale_reported = False
                while not self.stop.is_set():
                    try:
                        item = self.pending.get(timeout=0.25)
                    except queue.Empty:
                        if session.is_closed():
                            raise ConnectionError("Zenoh session closed")
                        with self.lock:
                            age = time.monotonic() - self.last_rx
                        # A silent sensor is not a broken subscription. Zenoh restores its TCP links.
                        if age >= self.cfg["reconnect_seconds"] and not stale_reported:
                            stale_reported = True
                            with self.lock:
                                self.stats["stale_events"] += 1
                                self.stats["last_error"] = f"no sample for {age:.1f}s; subscription retained"
                            LOG.warning("%s source stale; retaining Zenoh subscription", self.kind)
                        continue
                    try:
                        self.process(item)
                        stale_reported = False
                    except Exception as exc:
                        with self.lock:
                            self.stats["invalid"] += 1
                            self.stats["last_error"] = str(exc)
                        LOG.exception("invalid %s sample", self.kind)
                subscriber.undeclare()
            except Exception as exc:
                with self.lock:
                    self.stats["reconnects"] += 1
                    self.stats["last_error"] = str(exc)
                LOG.warning("%s reconnect: %s", self.kind, exc)
            finally:
                if session is not None:
                    session.close()
            self.stop.wait(0.5)


async def serve(cfg):
    loop = asyncio.get_running_loop()
    updated = asyncio.Event()
    diagnostics = dict(event_loop_lag_max_ms=0)
    async def watch_loop():
        while True:
            started = loop.time()
            await asyncio.sleep(.1)
            lag = max(0, (loop.time()-started-.1)*1000)
            diagnostics["event_loop_lag_max_ms"] = max(diagnostics["event_loop_lag_max_ms"], lag)
            if lag > 250:
                LOG.warning("HTTP event loop delayed %.1fms", lag)
    loop_watch = asyncio.create_task(watch_loop())
    recorder = RawRecorder(ROOT / "raw_data" / "pointcloud") if cfg.get("record_pointcloud", True) else None
    if recorder:
        recorder.thread.start()
    sources = {kind: Source(kind, cfg, lambda: loop.call_soon_threadsafe(updated.set),
                            recorder if kind == "pointcloud" else None)
               for kind in ("image", "pointcloud")}
    server = foxglove.start_server(name="Yunke | MC800S + XT-M60 | Zenoh", host=cfg["bind"],
                                   port=cfg["foxglove_port"], message_backlog_size=4)
    for source in sources.values():
        source.thread.start()
    app = web.Application()

    async def index(request):
        return web.FileResponse(ROOT / "pc" / "viewer.html", headers={"Cache-Control": "no-store"})

    async def status(request):
        return web.json_response({"time_ns": time.time_ns(),
                                  "diagnostics": dict(diagnostics),
                                  "recorder": recorder.status() if recorder else None,
                                  **{name: source.status() for name, source in sources.items()}},
                                 headers={"Cache-Control": "no-store"})

    async def latest(request):
        after = request.query.get("after", "")
        deadline = loop.time() + 1.0
        while True:
            # Clear first so an update between inspection and wait is not lost.
            updated.clear()
            source = sources["image"]
            with source.lock:
                frame = source.latest
            if frame and str(frame["frame_id"]) != after:
                break
            remaining = deadline - loop.time()
            if remaining <= 0:
                return web.Response(status=204, headers={"Cache-Control": "no-store"})
            try:
                await asyncio.wait_for(updated.wait(), remaining)
            except asyncio.TimeoutError:
                return web.Response(status=204, headers={"Cache-Control": "no-store"})
        age = time.monotonic() - frame["received_mono"]
        if age > cfg["stale_seconds"]:
            return web.Response(status=503, text="Camera data stale", headers={"Cache-Control": "no-store"})
        headers = {"Cache-Control": "no-store", "X-Frame-Id": str(frame["frame_id"]),
                   "X-Source-Seq": str(frame["seq"]), "X-Frame-Age-Ms": f"{age * 1000:.1f}",
                   "X-Jpeg-Sha256": frame["sha256"]}
        if request.path == "/api/image.pb":
            return web.Response(body=frame["payload"], content_type="application/x-protobuf", headers=headers)
        return web.Response(body=frame["data"], content_type="image/jpeg", headers=headers)

    app.router.add_get("/", index)
    app.router.add_get("/api/status", status)
    app.router.add_get("/latest.jpg", latest)
    app.router.add_get("/api/image.pb", latest)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, cfg["bind"], cfg["http_port"]).start()
    LOG.info("ready HTTP=%s:%s Foxglove=%s:%s", cfg["bind"], cfg["http_port"], cfg["bind"], cfg["foxglove_port"])
    try:
        while True:
            await asyncio.sleep(10)
            LOG.info("health %s", json.dumps({kind: source.status() for kind, source in sources.items()}))
    finally:
        loop_watch.cancel()
        for source in sources.values():
            source.stop.set()
        for source in sources.values():
            await asyncio.to_thread(source.thread.join, 3)
        if recorder:
            recorder.stop.set()
            await asyncio.to_thread(recorder.thread.join, 3)
        await runner.cleanup()
        server.stop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "pc.json")
    parser.add_argument("--http-port", type=int)
    parser.add_argument("--foxglove-port", type=int)
    parser.add_argument("--console", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    if args.http_port:
        cfg["http_port"] = args.http_port
    if args.foxglove_port:
        cfg["foxglove_port"] = args.foxglove_port
    (ROOT / "runtime").mkdir(exist_ok=True)
    handlers = [RotatingFileHandler(ROOT / "runtime" / "gateway.log", maxBytes=4_000_000,
                                    backupCount=3, encoding="utf-8")]
    if args.console:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers)
    try:
        asyncio.run(serve(cfg))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
