from __future__ import annotations
from dataclasses import dataclass, field
from collections import defaultdict
import math
from typing import Optional

@dataclass
class IdentityState:
    person_id: Optional[str]=None; name: str="Unknown"; confidence: float=0.0
    observations: int=0; votes: dict[str,float]=field(default_factory=dict); candidate_counts: dict[str,int]=field(default_factory=dict)

def cosine(a,b):
    dot=sum(x*y for x,y in zip(a,b)); na=math.sqrt(sum(x*x for x in a)); nb=math.sqrt(sum(y*y for y in b))
    return dot/(na*nb) if na and nb else 0.0

class IdentityManager:
    def __init__(self,threshold=.45,confirm_score=2.0,switch_margin=.4):
        self.threshold=threshold; self.confirm_score=confirm_score; self.switch_margin=switch_margin; self.states={}
    def observe(self,track_id,candidates,timestamp=None):
        state=self.states.setdefault(track_id,IdentityState())
        state.observations+=1
        for person,score in candidates:
            if score>=self.threshold:
                state.votes[person]=state.votes.get(person,0)+score
                state.candidate_counts[person]=state.candidate_counts.get(person,0)+1
        if state.votes:
            winner,score=max(state.votes.items(),key=lambda x:x[1]); current=state.votes.get(state.person_id,0)
            if state.person_id is None and score>=self.confirm_score or state.person_id and (winner==state.person_id or score>=current+self.switch_margin):
                state.person_id=winner; state.name=winner; state.confidence=min(1.0,score/max(state.candidate_counts.get(winner,1),1))
        return state
    def unknown(self,track_id): return self.states.setdefault(track_id,IdentityState())
    def merge_track(self,old_track,new_track):
        old=self.states.get(old_track); new=self.states.setdefault(new_track,IdentityState())
        if old:
            for k,v in old.votes.items():new.votes[k]=new.votes.get(k,0)+v
            for k,v in old.candidate_counts.items():new.candidate_counts[k]=new.candidate_counts.get(k,0)+v
            if old.person_id and not new.person_id:new.person_id, new.name=old.person_id,old.name
        return new
