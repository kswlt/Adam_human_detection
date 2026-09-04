from __future__ import annotations
from dataclasses import dataclass, field
import math

@dataclass(frozen=True)
class Detection:
    bbox: tuple[float, float, float, float]
    confidence: float = 1.0
    class_id: int = 0

@dataclass
class TrackState:
    track_id: int
    bbox: tuple[float, float, float, float]
    first_seen: float
    last_seen: float
    state: str = "TENTATIVE"
    age: int = 1
    hits: int = 1
    velocity: tuple[float, float] = (0.0, 0.0)
    identity: object = None
    history: list = field(default_factory=list)
    detection_confidence: float = 0.0

    @property
    def center(self):
        x1,y1,x2,y2 = self.bbox
        return ((x1+x2)/2, (y1+y2)/2)
    @property
    def foot_point(self):
        x1,_,x2,y2 = self.bbox
        return ((x1+x2)/2, y2)

def iou(a,b):
    ax1,ay1,ax2,ay2=a; bx1,by1,bx2,by2=b
    ix1,iy1=max(ax1,bx1),max(ay1,by1); ix2,iy2=min(ax2,bx2),min(ay2,by2)
    inter=max(0,ix2-ix1)*max(0,iy2-iy1)
    area=lambda z:max(0,z[2]-z[0])*max(0,z[3]-z[1])
    return inter/(area(a)+area(b)-inter) if area(a)+area(b)-inter else 0.0

class SimpleByteTracker:
    """Dependency-free ByteTrack-style IoU tracker for MVP/offline mode."""
    def __init__(self, track_buffer=30, match_iou=0.25, confirm_hits=2, weak_confirm_hits=4, weak_confidence=.30):
        self.track_buffer=track_buffer; self.match_iou=match_iou; self.confirm_hits=confirm_hits; self.weak_confirm_hits=weak_confirm_hits; self.weak_confidence=weak_confidence
        self.next_id=1; self.tracks={}
    def update(self, detections, timestamp):
        detections=[d for d in detections if d.class_id==0]
        unmatched=set(range(len(detections))); pairs=[]
        for tid,t in list(self.tracks.items()):
            best=max(unmatched, key=lambda i:iou(t.bbox,detections[i].bbox), default=None)
            if best is not None and iou(t.bbox,detections[best].bbox)>=self.match_iou:
                pairs.append((tid,best)); unmatched.remove(best)
        for tid,idx in pairs:
            t=self.tracks[tid]; old=t.center; t.bbox=detections[idx].bbox; new=t.center
            dt=max(1e-6,timestamp-t.last_seen); raw=((new[0]-old[0])/dt,(new[1]-old[1])/dt)
            t.velocity=(0.7*t.velocity[0]+0.3*raw[0],0.7*t.velocity[1]+0.3*raw[1])
            t.last_seen=timestamp; t.age+=1; t.hits+=1; t.detection_confidence=detections[idx].confidence
            required=self.weak_confirm_hits if t.detection_confidence<self.weak_confidence else self.confirm_hits
            t.state="CONFIRMED" if t.hits>=required else "TENTATIVE"
        for idx in unmatched:
            d=detections[idx]; tid=self.next_id; self.next_id+=1
            self.tracks[tid]=TrackState(tid,d.bbox,timestamp,timestamp,detection_confidence=d.confidence)
        for tid,t in list(self.tracks.items()):
            if t.last_seen < timestamp:
                t.state="LOST"
                if timestamp-t.last_seen>self.track_buffer/10:
                    t.state="REMOVED"; del self.tracks[tid]
        return [t for t in self.tracks.values() if t.state!="REMOVED"]
