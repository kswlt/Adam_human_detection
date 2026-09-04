from __future__ import annotations
import time
from .tracking import SimpleByteTracker,TrajectoryHistory,ConstantVelocityPredictor
from .analytics import WorkTimeAnalyzer,point_zone
from .face import IdentityManager
from .storage.writer import BatchWriter
class AnalyticsPipeline:
    def __init__(self,detector,recognizer=None,zones=(),track_buffer=30,history_seconds=30,writer=None):
        self.detector=detector; self.recognizer=recognizer; self.zones=tuple(zones); self.tracker=SimpleByteTracker(track_buffer); self.identity=IdentityManager(); self.predictor=ConstantVelocityPredictor(); self.history_seconds=history_seconds; self.people={}; self.frames=0; self.last_latency_ms=0; self.writer=writer
    def process(self,image,timestamp=None):
        timestamp=time.time() if timestamp is None else timestamp; begin=time.perf_counter(); detections=self.detector.detect(image); tracks=self.tracker.update(detections,timestamp); result=[]
        for track in tracks:
            ident=self.identity.observe(track.track_id,self.recognizer.recognize(image,track.bbox) if self.recognizer else []) if self.recognizer else self.identity.unknown(track.track_id); track.identity=ident
            item=self.people.setdefault(track.track_id,{'history':TrajectoryHistory(self.history_seconds),'work':WorkTimeAnalyzer(),'identity':ident})
            item['identity']=ident; item['history'].add(timestamp,track.foot_point); zone=point_zone(track.foot_point,self.zones); item['zone']=zone.name if zone else None; item['work'].observe(ident.person_id,timestamp,item['zone'])
            if self.writer and ident.person_id:self.writer.submit((timestamp,ident.person_id,track.track_id,track.foot_point[0],track.foot_point[1],None,None,item['zone']))
            result.append({'track_id':track.track_id,'person_id':ident.person_id,'name':ident.name,'confidence':ident.confidence,'bbox':track.bbox,'foot_point':track.foot_point,'zone':item['zone'],'history':item['history'].as_list(),'predictions':self.predictor.predict(item['history'])})
        self.frames+=1; self.last_latency_ms=(time.perf_counter()-begin)*1000; return result
    def status(self):
        return {'frames':self.frames,'latency_ms':self.last_latency_ms,'people':[{'track_id':i,'person_id':v['identity'].person_id,'name':v['identity'].name,'zone':v.get('zone')} for i,v in self.people.items()]}
