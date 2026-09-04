"""One-command Windows validation for the official BoxMOT OSNet checkpoint."""
from pathlib import Path
import hashlib, json, urllib.request

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "models" / "reid" / "osnet_x0_25_msmt17.pt"


def main():
    out = {"model": str(MODEL), "exists": MODEL.exists(), "gateway": {}, "embedding": {}}
    if MODEL.exists():
        out.update(file_size=MODEL.stat().st_size, sha256=hashlib.sha256(MODEL.read_bytes()).hexdigest(), source="BoxMOT official model catalog", training_dataset="MSMT17")
        import cv2, numpy as np
        from boxmot import ReIDModel
        import torch
        model = ReIDModel(str(MODEL), device="cuda:0", half=False)
        raw = urllib.request.urlopen("http://127.0.0.1:8080/latest.jpg", timeout=8).read()
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        h, w = image.shape[:2]; box = np.array([[0, 0, w, h]], dtype=np.float32)
        a = np.asarray(model.embed(image, boxes=box))[0].reshape(-1)
        norm = float(np.linalg.norm(a)); b = a / max(norm, 1e-8)
        out["gateway"] = {"bytes": len(raw), "shape": [h, w]}
        out["embedding"] = {"shape": list(b.shape), "norm": float(np.linalg.norm(b)), "finite": bool(np.isfinite(b).all()), "self_similarity": float(np.dot(b, b)), "device": str(torch.cuda.get_device_name(0))}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if not out["exists"]: raise SystemExit("REID_UNHEALTHY: model missing; run tools/download_reid_model.py")


if __name__ == "__main__": main()
