"""Daily bounded gallery with reject/ambiguous outcomes; no unconditional nearest match."""
from dataclasses import dataclass, field
from typing import Optional
import numpy as np


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
