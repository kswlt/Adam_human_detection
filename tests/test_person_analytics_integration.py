import unittest
import tempfile
from pathlib import Path
from pc.person_analytics.app import AnalyticsApp
from pc.person_analytics.tracking import Detection
from pc.person_analytics.pipeline import AnalyticsPipeline
from pc.person_analytics.analytics import Zone
from pc.person_analytics.storage import AnalyticsDatabase
from pc.person_analytics.storage.writer import BatchWriter

class FakeDetector:
 def detect(self,image): return [Detection((0,0,10,10))]
class FakeRecognizer:
 def recognize(self,image,bbox=None): return [('张三',.9)]
class IntegrationTests(unittest.TestCase):
 def test_pipeline_accepts_synthetic_frames_without_cv2(self):
  a=AnalyticsApp('synthetic',FakeDetector()); a.process(b'jpeg',0); a.process(b'jpeg',1)
  s=a.status(); self.assertEqual(s['people'][0]['track_id'],1); self.assertGreaterEqual(s['ai_fps'],0)
 def test_pipeline_emits_history_prediction_and_footpoint_zone(self):
  pipe=AnalyticsPipeline(FakeDetector(),zones=[Zone('z','工作区',((0,0),(20,0),(20,20),(0,20)))])
  first=pipe.process(None,0); second=pipe.process(None,1)
  self.assertEqual(second[0]['zone'],'工作区'); self.assertEqual(len(second[0]['history']),2); self.assertEqual(second[0]['predictions'][0][1],5.0)
 def test_known_pipeline_persists_trajectory_and_session(self):
  with tempfile.TemporaryDirectory() as folder:
   db=AnalyticsDatabase(str(Path(folder)/'a.db')); w=BatchWriter(db); w.thread.start(); a=AnalyticsApp('synthetic',FakeDetector(),FakeRecognizer(),w); a.process(b'jpeg',0); a.process(b'jpeg',1); a.process(b'jpeg',2); a.close(3); w.stop.set(); w.thread.join(2); db.commit()
   self.assertEqual(db.db.execute('select count(*) from trajectory_points').fetchone()[0],3); self.assertEqual(db.db.execute('select count(*) from person_sessions').fetchone()[0],1); self.assertEqual(db.db.execute('select person_id from trajectory_points where person_id is not null limit 1').fetchone()[0],'张三'); db.close()
