"""Optional ONNX body ReID interface with explicit unavailable diagnostics."""
from pathlib import Path
import time


class AppearanceEncoder:
    def __init__(self, model_path="models/reid/osnet_x0_25_msmt17.pt", providers=None, device="cuda:0", require_gpu=True):
        self.model_path = str(model_path); self.providers = providers or ["CUDAExecutionProvider", "CPUExecutionProvider"]; self.device=device; self.require_gpu=require_gpu
        self.session = None; self.runtime = None; self.last_error = None; self.last_ms = 0.0; self.calls = 0; self.embedding_dim=None
        if Path(self.model_path).exists():
            try:
                if Path(self.model_path).suffix.lower() == ".pt":
                    from boxmot import ReIDModel
                    self.runtime = ReIDModel(self.model_path, device=self.device, half=False)
                    self.embedding_dim = 256
                else:
                    import onnxruntime as ort
                    self.session = ort.InferenceSession(self.model_path, providers=self.providers)
                    active = self.session.get_providers()
                    if self.require_gpu and "CUDAExecutionProvider" not in active: raise RuntimeError("REID_UNHEALTHY: CUDAExecutionProvider not active: %s" % active)
            except Exception as exc:
                self.last_error = str(exc)
        else:
            self.last_error = "ReID model missing: %s" % self.model_path

    @property
    def available(self): return self.session is not None or self.runtime is not None

    def encode(self, frame, bbox):
        if not self.available: return None
        import cv2, numpy as np
        started = time.perf_counter(); x1,y1,x2,y2 = map(int,bbox)
        crop = frame[max(0,y1):max(0,y2), max(0,x1):max(0,x2)]
        if crop.size == 0: return None
        if self.runtime is not None:
            out = np.asarray(self.runtime.embed(frame, boxes=np.asarray([[x1,y1,x2,y2]], dtype=np.float32)))[0].reshape(-1)
        else:
            crop = cv2.cvtColor(cv2.resize(crop,(128,256)), cv2.COLOR_BGR2RGB).astype(np.float32)/255.0
            inp = crop.transpose(2,0,1)[None]
            out = self.session.run(None, {self.session.get_inputs()[0].name: inp})[0].reshape(-1)
        self.embedding_dim = int(out.size)
        norm = float(np.linalg.norm(out)); self.calls += 1; self.last_ms = (time.perf_counter()-started)*1000
        return (out/norm).tolist() if norm else None

    def diagnostics(self):
        active = self.session.get_providers() if self.session else (["CUDAExecutionProvider"] if self.runtime is not None and str(self.device).startswith("cuda") else [])
        return {"enabled": self.available, "model": self.model_path, "model_loaded": self.available, "reid_model": self.model_path, "reid_provider": active[0] if active else None, "reid_device": self.device, "providers": active, "embedding_dim": self.embedding_dim, "inference_ms": self.last_ms, "last_error": self.last_error, "calls": self.calls}
