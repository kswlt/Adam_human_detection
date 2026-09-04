"""Daily bounded gallery with reject/ambiguous outcomes; no unconditional nearest match."""
from dataclasses import dataclass, field
from typing import Optional
import numpy as np
import json


@dataclass
class GalleryEntry:
    global_person_id: str
    samples: list = field(default_factory=list)


class DailyAppearanceGallery:
    def __init__(self, threshold=.78, margin=.08, max_samples=20):
        self.threshold, self.margin, self.max_samples = threshold, margin, max_samples
        self.entries = {}

    def add(self, global_person_id, embedding):
        if embedding is None: return
        e = self.entries.setdefault(global_person_id, GalleryEntry(global_person_id))
        if len(e.samples) < self.max_samples: e.samples.append(list(embedding))

    def match(self, embedding):
        if embedding is None or not self.entries: return {"status":"NEW", "global_person_id":None, "best":0.0, "second":0.0, "margin":0.0}
        v=np.asarray(embedding,dtype=np.float32); v/=max(float(np.linalg.norm(v)),1e-8); scores=[]
        for gid,e in self.entries.items():
            best=max(float(np.dot(v, np.asarray(s,dtype=np.float32)/max(float(np.linalg.norm(s)),1e-8))) for s in e.samples)
            scores.append((best,gid))
        scores.sort(reverse=True); best,gid=scores[0]; second=scores[1][0] if len(scores)>1 else 0.0; margin=best-second
        status="MATCHED" if best >= self.threshold and margin >= self.margin else ("AMBIGUOUS" if best >= self.threshold else "NEW")
        return {"status":status,"global_person_id":gid if status=="MATCHED" else None,"best":best,"second":second,"margin":margin}

    def save(self, path, model_id="osnet_x0_25_msmt17_v1"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"model_id":model_id,"entries":{k:e.samples for k,e in self.entries.items()}}, f)

    def load(self, path, model_id="osnet_x0_25_msmt17_v1"):
        try:
            with open(path, "r", encoding="utf-8") as f: payload=json.load(f)
            if payload.get("model_id") != model_id: return False
            for gid,samples in payload.get("entries",{}).items():
                for sample in samples[:self.max_samples]: self.add(gid,sample)
            return True
        except (OSError, ValueError, TypeError): return False
