"""Stable daily identities, deliberately separate from detector track IDs."""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional
import uuid
import json


@dataclass
class GlobalPerson:
    global_person_id: str
    known_person_id: Optional[str] = None
    name: str = "Unknown"
    first_seen_today: float = 0.0
    last_seen: float = 0.0
    current_track_id: Optional[int] = None
    identity_status: str = "unknown"
    identity_source: str = "unknown"
    confidence: float = 0.0
    track_ids: list = field(default_factory=list)


class GlobalPersonManager:
    """Conservative identity layer. A track is never exposed as a business ID."""
    def __init__(self, day=None, prefix="DAY"):
        self.day = day or date.today().strftime("%Y%m%d")
        self.prefix = prefix
        self.people = {}
        self.track_to_global = {}
        self.next_number = 1
        self.track_recoveries = 0
        self.merge_count = 0

    def _new(self, timestamp):
        gid = "%s_%s_%04d" % (self.prefix, self.day, self.next_number)
        self.next_number += 1
        self.people[gid] = GlobalPerson(gid, first_seen_today=timestamp, last_seen=timestamp)
        return self.people[gid]

    def update(self, track_id, timestamp, face_state=None):
        gid = self.track_to_global.get(track_id)
        person = self.people.get(gid) if gid else None
        known = getattr(face_state, "person_id", None) if face_state is not None else None
        if person is None and known:
            person = next((p for p in self.people.values() if p.known_person_id == known and p.current_track_id != track_id), None)
            if person is not None:
                self.track_to_global[track_id] = person.global_person_id
        if person is None:
            person = self._new(timestamp)
            self.track_to_global[track_id] = person.global_person_id
        if track_id not in person.track_ids:
            if person.current_track_id is not None and person.current_track_id != track_id:
                self.track_recoveries += 1
            person.track_ids.append(track_id)
        person.current_track_id, person.last_seen = track_id, timestamp
        if face_state is not None and known:
            person.known_person_id = face_state.person_id
            person.name = face_state.name
            person.identity_status = "confirmed"
            person.identity_source = "face"
            person.confidence = max(person.confidence, float(face_state.confidence))
        return person

    def promote(self, track_id, known_person_id, name, confidence=1.0):
        gid = self.track_to_global.get(track_id)
        if not gid: return None
        person = self.people[gid]
        person.known_person_id, person.name = known_person_id, name
        person.identity_status, person.identity_source, person.confidence = "confirmed", "face", confidence
        return person

    def attach(self, track_id, global_person_id, timestamp):
        person = self.people.get(global_person_id)
        if person is None: return None
        # One physical camera must not bind two simultaneously visible tracks to one person.
        if person.current_track_id not in (None, track_id) and timestamp - person.last_seen < 5.0:
            return None
        old = self.track_to_global.get(track_id)
        if old != global_person_id: self.track_recoveries += 1
        self.track_to_global[track_id] = global_person_id
        if track_id not in person.track_ids: person.track_ids.append(track_id)
        person.current_track_id, person.last_seen = track_id, timestamp
        return person

    def snapshot(self):
        return [dict(global_person_id=p.global_person_id, known_person_id=p.known_person_id,
                     name=p.name, first_seen_today=p.first_seen_today, last_seen=p.last_seen,
                     current_track_id=p.current_track_id, identity_status=p.identity_status,
                     identity_source=p.identity_source, confidence=p.confidence,
                     track_ids=list(p.track_ids)) for p in self.people.values()]

    def diagnostics(self):
        return {"active_global_persons": len(self.people), "daily_global_persons": len(self.people),
                "track_recoveries": self.track_recoveries, "global_merge_count": self.merge_count,
                "global_person_churn": len(self.people)}

    def save(self, path):
        payload = {"day": self.day, "next_number": self.next_number,
                   "people": [p.__dict__ for p in self.people.values()],
                   "track_to_global": self.track_to_global}
        with open(path, "w", encoding="utf-8") as f: json.dump(payload, f, ensure_ascii=False, indent=2)

    def load(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f: payload = json.load(f)
            if payload.get("day") != self.day: return False
            self.next_number = int(payload.get("next_number", 1)); self.people = {}
            for raw in payload.get("people", []): self.people[raw["global_person_id"]] = GlobalPerson(**raw)
            self.track_to_global = {int(k):v for k,v in payload.get("track_to_global", {}).items()}
            return True
        except (OSError, ValueError, TypeError, KeyError):
            return False
