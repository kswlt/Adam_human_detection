from __future__ import annotations
from collections import deque
import math

class TrajectoryHistory:
    def __init__(self, seconds=30, smoothing_alpha=1.0): self.seconds=seconds; self.points=deque(); self.raw_points=deque(); self.smoothing_alpha=smoothing_alpha
    def add(self,timestamp,point):
        raw=(timestamp,float(point[0]),float(point[1])); self.raw_points.append(raw)
        if self.points:
            _,px,py=self.points[-1]; a=self.smoothing_alpha; point=(a*raw[1]+(1-a)*px,a*raw[2]+(1-a)*py)
        self.points.append((timestamp,float(point[0]),float(point[1])))
        while self.points and timestamp-self.points[0][0]>self.seconds: self.points.popleft()
        while self.raw_points and timestamp-self.raw_points[0][0]>self.seconds: self.raw_points.popleft()
    def as_list(self): return list(self.points)
    def raw_as_list(self): return list(self.raw_points)

class ConstantVelocityPredictor:
    def __init__(self,min_movement=2.0,steps=None,max_speed=2000.0): self.min_movement=min_movement; self.steps=tuple(steps or (.5,1,1.5,2,3)); self.max_speed=float(max_speed)
    def predict(self, history, steps=None):
        steps=self.steps if steps is None else steps
        pts=history.as_list()
        if len(pts)<2: return []
        a,b=pts[-2],pts[-1]; dt=max(1e-6,b[0]-a[0]); vx=(b[1]-a[1])/dt; vy=(b[2]-a[2])/dt
        if math.hypot(vx,vy)>self.max_speed: return []
        if math.hypot(vx,vy)*dt < self.min_movement: vx=vy=0.0
        return [(float(s),b[1]+vx*s,b[2]+vy*s) for s in steps]
