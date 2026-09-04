from __future__ import annotations
from collections import deque
import math

class TrajectoryHistory:
    def __init__(self, seconds=30): self.seconds=seconds; self.points=deque()
    def add(self,timestamp,point):
        self.points.append((timestamp,float(point[0]),float(point[1])))
        while self.points and timestamp-self.points[0][0]>self.seconds: self.points.popleft()
    def as_list(self): return list(self.points)

class ConstantVelocityPredictor:
    def __init__(self,min_movement=2.0,steps=None): self.min_movement=min_movement; self.steps=tuple(steps or (.5,1,1.5,2,3))
    def predict(self, history, steps=None):
        steps=self.steps if steps is None else steps
        pts=history.as_list()
        if len(pts)<2: return [(float(dt),pts[-1][1],pts[-1][2]) for dt in steps] if pts else []
        a,b=pts[-2],pts[-1]; dt=max(1e-6,b[0]-a[0]); vx=(b[1]-a[1])/dt; vy=(b[2]-a[2])/dt
        if math.hypot(vx,vy)*dt < self.min_movement: vx=vy=0.0
        return [(float(s),b[1]+vx*s,b[2]+vy*s) for s in steps]
