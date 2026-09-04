"""Optional ONNX body ReID interface with explicit unavailable diagnostics."""
from pathlib import Path
import time


class AppearanceEncoder:
    def __init__(self, model_path="models/osnet_x0_25.onnx", providers=None):
        self.model_path = str(model_path); self.providers = providers or ["CUDAExecutionProvider", "CPUExecutionProvider"]
        self.session = None; self.last_error = None; self.last_ms = 0.0; self.calls = 0
        if Path(self.model_path).exists():
            try:
                import onnxruntime as ort
                self.session = ort.InferenceSession(self.model_path, providers=self.providers)
            except Exception as exc:
                self.last_error = str(exc)
        else:
            self.last_error = "ReID model missing: %s" % self.model_path

    @property
    def available(self): return self.session is not None

    def encode(self, frame, bbox):
        if not self.session: return None
        import cv2, numpy as np
        started = time.perf_counter(); x1,y1,x2,y2 = map(int,bbox)
        crop = frame[max(0,y1):max(0,y2), max(0,x1):max(0,x2)]
        if crop.size == 0: return None
        crop = cv2.cvtColor(cv2.resize(crop,(128,256)), cv2.COLOR_BGR2RGB).astype(np.float32)/255.0
        inp = crop.transpose(2,0,1)[None]
        out = self.session.run(None, {self.session.get_inputs()[0].name: inp})[0].reshape(-1)
        norm = float(np.linalg.norm(out)); self.calls += 1; self.last_ms = (time.perf_counter()-started)*1000
        return (out/norm).tolist() if norm else None

    def diagnostics(self):
        return {"enabled": self.available, "model": self.model_path, "providers": self.session.get_providers() if self.session else [], "last_error": self.last_error, "calls": self.calls, "last_ms": self.last_ms}
