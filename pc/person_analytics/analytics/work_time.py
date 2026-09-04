from collections import defaultdict
class WorkTimeAnalyzer:
    def __init__(self,grace_seconds=5): self.grace=grace_seconds; self.sessions={}; self.totals=defaultdict(float)
    def observe(self,person_id,timestamp,zone=None):
        if not person_id:return
        s=self.sessions.get(person_id)
        if not s or timestamp-s['last_seen']>self.grace:
            if s:self._close(person_id,s)
            s={'start':timestamp,'last_seen':timestamp,'max_gap':0.0,'zones':defaultdict(float)}; self.sessions[person_id]=s
        delta=max(0.0,timestamp-s['last_seen']); s['max_gap']=max(s['max_gap'],delta)
        self.totals[(person_id,'visible')]+=delta
        if zone:self.totals[(person_id,zone)]+=delta; s['zones'][zone]+=delta
        s['last_seen']=timestamp
    def _close(self,p,s): self.totals[(p,'session')]+=s['last_seen']-s['start']
    def close_expired(self,timestamp):
        for p,s in list(self.sessions.items()):
            if timestamp-s['last_seen']>self.grace:self._close(p,s); del self.sessions[p]
    def seconds(self,person_id,kind):return self.totals[(person_id,kind)]

