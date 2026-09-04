from __future__ import annotations
from pathlib import Path
import hashlib, json
import math
class FaceDatabase:
    """Local gallery index; embedding extraction is supplied by an optional backend."""
    def __init__(self,root="data/persons",index_path="data/face_db/index.json"):
        self.root=Path(root); self.index_path=Path(index_path); self.records={}; self.last_scan={}
    def scan(self,embedder=None,rebuild=False):
        previous={} if rebuild or not self.index_path.exists() else json.loads(self.index_path.read_text(encoding='utf-8'))
        self.records={}; invalid=[]; image_count=0; valid_count=0; cache_hits=0
        for person_dir in sorted(self.root.glob('*')) if self.root.exists() else []:
            if not person_dir.is_dir():continue
            vectors=[]
            for image in sorted(person_dir.iterdir()):
                if image.suffix.lower() not in {'.jpg','.jpeg','.png','.bmp'}:continue
                image_count+=1
                digest=hashlib.sha256(image.read_bytes()).hexdigest(); old=previous.get(str(image))
                if old and old.get('sha256')==digest:vectors.append(old['embedding']); cache_hits+=1; continue
                try:
                    if embedder is None: raise RuntimeError('face embedder unavailable')
                    vectors.append(list(embedder(image)))
                except Exception as exc: invalid.append({'person':person_dir.name,'image':str(image),'error':str(exc)})
                else: previous[str(image)]={'sha256':digest,'embedding':vectors[-1]}
            if vectors:
                valid_count+=len(vectors)
                centroid=[sum(v[i] for v in vectors)/len(vectors) for i in range(len(vectors[0]))]
                norm=math.sqrt(sum(v*v for v in centroid)) or 1.0
                self.records[person_dir.name]={'embeddings':vectors,'centroid':[v/norm for v in centroid]}
        self.index_path.parent.mkdir(parents=True,exist_ok=True); self.index_path.write_text(json.dumps(previous,ensure_ascii=False),encoding='utf-8')
        self.last_scan={'persons':len(self.records),'images':image_count,'valid_embeddings':valid_count,'invalid_images':len(invalid),'invalid':invalid,'cache_hits':cache_hits,'database_updated':bool(image_count-cache_hits or rebuild)}
        return {'persons':len(self.records),'valid_faces':valid_count,'invalid':invalid,'images':image_count,'cache_hits':cache_hits,'database_updated':self.last_scan['database_updated']}
