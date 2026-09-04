import tempfile, unittest
from pathlib import Path
from pc.person_analytics.tracking import Detection, SimpleByteTracker,TrajectoryHistory,ConstantVelocityPredictor
from pc.person_analytics.face import IdentityManager
from pc.person_analytics.analytics import Zone,point_zone,WorkTimeAnalyzer
from pc.person_analytics.storage import AnalyticsDatabase
from pc.person_analytics.face import FaceDatabase
from pc.person_analytics.trajectory import HomographyProjector

class CoreTests(unittest.TestCase):
 def test_tracking_and_prediction(self):
  t=SimpleByteTracker(track_buffer=30); a=t.update([Detection((0,0,10,10))],0); b=t.update([Detection((1,0,11,10))],1)
  self.assertEqual(a[0].track_id,b[0].track_id); h=TrajectoryHistory(); h.add(0,(0,0)); h.add(1,(10,0)); self.assertAlmostEqual(ConstantVelocityPredictor().predict(h,[1])[0][1],20)
 def test_identity_temporal_fusion_and_merge(self):
  m=IdentityManager(confirm_score=1); self.assertEqual(m.observe(1,[('张三',.8)]).name,'Unknown'); self.assertEqual(m.observe(1,[('张三',.8)]).name,'张三'); self.assertEqual(m.merge_track(1,2).person_id,'张三')
 def test_zone_and_timestamp_work_time(self):
  z=Zone('work','工作台',((0,0),(10,0),(10,10),(0,10))); self.assertEqual(point_zone((5,5),[z]).zone_id,'work'); w=WorkTimeAnalyzer(5); w.observe('p',0,'work'); w.observe('p',2,'work'); w.observe('p',5,'work'); self.assertEqual(w.seconds('p','visible'),5)
 def test_database_schema_and_write(self):
  with tempfile.TemporaryDirectory() as folder:
   d=AnalyticsDatabase(str(Path(folder)/'analytics.db')); d.add_trajectory((1,'p',2,3,4,None,None,'work')); d.commit(); self.assertEqual(d.db.execute('select count(*) from trajectory_points').fetchone()[0],1); d.close()
 def test_face_db_incremental_scan_and_image_mode(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder)/'persons'; (root/'张三').mkdir(parents=True); (root/'张三'/'001.jpg').write_bytes(b'not-an-image')
   db=FaceDatabase(str(root),str(Path(folder)/'index.json')); r=db.scan(embedder=lambda p:[1,0]); self.assertEqual(r['persons'],1); self.assertEqual(r['valid_faces'],1); self.assertEqual(FaceDatabase(str(root),str(Path(folder)/'index.json')).scan()['valid_faces'],1)
 def test_projector_without_calibration_is_explicitly_image_mode(self):
  p=HomographyProjector(); self.assertEqual(p.mode,'image'); self.assertEqual(p.project((3,4)),(3.0,4.0))

if __name__=='__main__':unittest.main()
