"""Offline/Gateway MVP runner for person analytics."""
from __future__ import annotations
import argparse, asyncio, json, time, urllib.request, urllib.error, traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .detection import PersonDetector
from .tracking import SimpleByteTracker, UltralyticsTracker, TrajectoryHistory, ConstantVelocityPredictor
from .analytics import Zone, point_zone, WorkTimeAnalyzer
from .face import IdentityManager
from .face import FaceDatabase, FaceRecognizer
from .storage import AnalyticsDatabase
from .storage.writer import BatchWriter
from .gpu import diagnose

HTML='''<!doctype html><meta charset="utf-8"><title>实时人员分析</title><style>body{background:#101820;color:#eee;font:16px sans-serif;margin:2em}#wrap{position:relative;width:min(90vw,1280px)}canvas{width:100%;border:1px solid #456}table{border-collapse:collapse}td,th{padding:8px 16px;border-bottom:1px solid #345}</style><h1>实时人员分析</h1><p id="m">加载中</p><div id="wrap"><canvas id="v"></canvas></div><h2>当前人员</h2><table><thead><tr><th>姓名</th><th>Track</th><th>置信度</th><th>区域</th><th>出现时长</th></tr></thead><tbody id="p"></tbody></table><h2>今日统计</h2><pre id="d"></pre><script>async function tick(){let s=await fetch('/api/analytics').then(x=>x.json());m.textContent=`Camera FPS ${s.camera_fps.toFixed(1)} | AI FPS ${s.ai_fps.toFixed(1)} | latency ${s.latency_ms.toFixed(1)}ms`;let im=new Image();im.onload=()=>{v.width=im.naturalWidth;v.height=im.naturalHeight;let c=v.getContext('2d');c.drawImage(im,0,0);s.people.forEach(x=>{let b=x.bbox;c.strokeStyle='#00ff88';c.lineWidth=3;c.strokeRect(b[0],b[1],b[2]-b[0],b[3]-b[1]);c.fillStyle='#00ff88';c.font='22px sans-serif';c.fillText(`${x.name} / #${x.track_id}`,b[0],Math.max(24,b[1]-6));c.strokeStyle='#00aaff';c.beginPath();x.history.forEach((q,i)=>i?c.lineTo(q[1],q[2]):c.moveTo(q[1],q[2]));c.stroke();c.strokeStyle='#ff9900';c.setLineDash([8,8]);c.beginPath();x.predictions.forEach((q,i)=>i?c.lineTo(q[1],q[2]):c.moveTo(q[1],q[2]));c.stroke();c.setLineDash([])});};im.src='/frame.jpg?t='+Date.now();p.innerHTML=s.people.map(x=>`<tr><td>${x.name}</td><td>#${x.track_id}</td><td>${(x.confidence*100).toFixed(1)}%</td><td>${x.zone||'-'}</td><td>${x.visible_seconds.toFixed(1)}s</td></tr>`).join('');d.textContent=JSON.stringify(await fetch('/api/analytics/today').then(x=>x.json()),null,2)}setInterval(tick,500);tick()</script>'''

def load_config(path):
    try:
        import yaml
        return yaml.safe_load(Path(path).read_text(encoding='utf-8')) or {}
    except (ImportError, OSError):
        return {}

class AnalyticsApp:
    def __init__(self, source, detector=None, recognizer=None, writer=None, zones=(), face_interval_unknown=.5, face_interval_known=3.0, track_buffer=30, history_seconds=30, prediction_steps=None, minimum_movement=2.0, grace_seconds=5.0, inference_max_width=1920, confirmed_only=False, confirm_hits=2, weak_confirm_hits=4, weak_confidence=.30, tracker=None, display_history_seconds=8, smoothing_alpha=.35):
        self.source=source; self.detector=detector or PersonDetector(); self.recognizer=recognizer; self.writer=writer; self.zones=tuple(zones); self.face_interval_unknown=face_interval_unknown; self.face_interval_known=face_interval_known; self.tracker=tracker or SimpleByteTracker(track_buffer,confirm_hits=confirm_hits,weak_confirm_hits=weak_confirm_hits,weak_confidence=weak_confidence); self.confirmed_only=confirmed_only; self.display_history_seconds=display_history_seconds; self.smoothing_alpha=smoothing_alpha; self.identity=IdentityManager(); self.predictor=ConstantVelocityPredictor(minimum_movement,prediction_steps); self.history_seconds=history_seconds; self.grace_seconds=grace_seconds; self.inference_max_width=inference_max_width; self.people={}; self.last_frame=b''; self.camera_times=[]; self.ai_times=[]; self.detector_times=[]; self.face_times=[]; self.latency_ms=0; self.dropped_frames=0; self.queue_size=0; self.source_stats={'healthy':False,'age_seconds':None,'last_error':None}; self.face_futures={}; self.face_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='analytics-face') if recognizer is not None and hasattr(recognizer,'load') else None
    def set_source_stats(self, queue_size=0, dropped_frames=0, **source_stats):
        self.queue_size=queue_size; self.dropped_frames=dropped_frames; self.source_stats.update(source_stats)
    def _recognize_job(self,image,bbox):
        started=time.perf_counter(); result=self.recognizer.recognize(image,bbox); return result,time.perf_counter()-started
    def _drain_face_results(self):
        for track_id,item in list(self.face_futures.items()):
            future,observed_timestamp=item
            if not future.done(): continue
            try: candidates,elapsed=future.result()
            except Exception:
                traceback.print_exc(); raise
            self.face_times.append(elapsed)
            state=self.identity.observe(track_id,candidates,observed_timestamp)
            if track_id in self.people:self.people[track_id]['face_state']=state
            del self.face_futures[track_id]
    def process(self,image,timestamp=None):
        timestamp=time.time() if timestamp is None else timestamp; started=time.perf_counter()
        source_image=image
        if isinstance(image,bytes):
            try:
                import cv2, numpy as np
                decoded=cv2.imdecode(np.frombuffer(image,dtype=np.uint8),cv2.IMREAD_COLOR)
                if decoded is not None: source_image=decoded
            except ImportError:
                pass
        full_image=source_image
        face_scale_x=face_scale_y=1.0
        if hasattr(source_image,'shape') and self.inference_max_width and source_image.shape[1]>self.inference_max_width:
            import cv2
            scale=self.inference_max_width/source_image.shape[1]
            face_scale_x=face_scale_y=1.0/scale
            source_image=cv2.resize(source_image,(self.inference_max_width,int(source_image.shape[0]*scale)),interpolation=cv2.INTER_AREA)
        if self.face_executor:self._drain_face_results()
        detector_started=time.perf_counter(); detections=self.detector.detect(source_image); self.detector_times.append(time.perf_counter()-detector_started); tracks=self.tracker.update(detections,timestamp,image=source_image) if isinstance(self.tracker,UltralyticsTracker) else self.tracker.update(detections,timestamp)
        active=[]
        for t in tracks:
            if t.last_seen != timestamp:
                continue
            if self.confirmed_only and t.state != 'CONFIRMED':
                continue
            person=self.people.setdefault(t.track_id,{'history':TrajectoryHistory(self.history_seconds,self.smoothing_alpha),'work':WorkTimeAnalyzer(self.grace_seconds),'name':'Unknown','person_id':None,'confidence':0.0,'zone':None,'last_zone':None,'last_face':-1e9,'face_state':self.identity.unknown(t.track_id)})
            interval=self.face_interval_known if person['person_id'] else self.face_interval_unknown
            if self.recognizer is not None and timestamp-person['last_face']>=interval:
                if self.face_executor:
                    if t.track_id not in self.face_futures:
                        bbox_full=(t.bbox[0]*face_scale_x,t.bbox[1]*face_scale_y,t.bbox[2]*face_scale_x,t.bbox[3]*face_scale_y)
                        self.face_futures[t.track_id]=(self.face_executor.submit(self._recognize_job,full_image.copy(),bbox_full),timestamp); person['last_face']=timestamp
                    state=person['face_state']
                else:
                    face_started=time.perf_counter()
                    bbox_full=(t.bbox[0]*face_scale_x,t.bbox[1]*face_scale_y,t.bbox[2]*face_scale_x,t.bbox[3]*face_scale_y)
                    try: state=self.identity.observe(t.track_id,self.recognizer.recognize(full_image,bbox_full),timestamp)
                    except Exception:
                        traceback.print_exc()
                        raise
                    finally: self.face_times.append(time.perf_counter()-face_started)
                    person['last_face']=timestamp; person['face_state']=state
            else: state=self.identity.unknown(t.track_id)
            if self.face_executor: state=person['face_state']
            t.identity=state
            person['history'].add(timestamp,t.foot_point); person['name']=state.name; person['person_id']=state.person_id; person['confidence']=state.confidence
            zone=point_zone(t.foot_point,self.zones); person['zone']=zone.name if zone else None
            if self.writer:
                if state.person_id: self.writer.submit(('__person__',state.person_id,state.name,timestamp))
                self.writer.submit(('__track__',t.track_id,state.person_id,t.first_seen,timestamp,t.state))
                if person['zone'] != person['last_zone']:
                    if person['last_zone'] is not None: self.writer.submit(('__zone__',timestamp,state.person_id,t.track_id,person['last_zone'],'exit'))
                    if person['zone'] is not None: self.writer.submit(('__zone__',timestamp,state.person_id,t.track_id,person['zone'],'enter'))
                    person['last_zone']=person['zone']
            person['work'].observe(state.person_id,timestamp,person['zone'])
            if self.writer:
                self.writer.submit((timestamp,state.person_id,t.track_id,t.foot_point[0],t.foot_point[1],None,None,person['zone']))
            active.append({'name':person['name'],'person_id':state.person_id,'track_id':t.track_id,'confidence':state.confidence,'detection_confidence':t.detection_confidence,'bbox':t.bbox,'zone':person['zone'],'visible_seconds':person['work'].seconds(state.person_id,'visible') if state.person_id else 0.0,'history':person['history'].as_list(),'predictions':self.predictor.predict(person['history'])})
        for person in self.people.values(): person['work'].close_expired(timestamp)
        visible_tracks=[track for track in tracks if not self.confirmed_only or track.state=='CONFIRMED']
        self.last_frame=self._jpeg(source_image); self.camera_times.append(timestamp); self.ai_times.append(time.perf_counter())
        self.camera_times=self.camera_times[-30:]; self.ai_times=self.ai_times[-30:]; self.detector_times=self.detector_times[-30:]; self.face_times=self.face_times[-30:]; self.latency_ms=(time.perf_counter()-started)*1000
        return active
    def _render(self,image,tracks):
        if isinstance(image,bytes):return image
        import cv2
        out=image.copy()
        for t in tracks:
            x1,y1,x2,y2=map(int,t.bbox); name=t.identity.name if t.identity else 'Unknown'; cv2.rectangle(out,(x1,y1),(x2,y2),(0,220,80),2); cv2.putText(out,f'{name} / #{t.track_id}',(x1,max(20,y1-8)),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,255,120),2)
            hist=self.people.get(t.track_id,{}).get('history');
            if hist:
                pts=[(int(x),int(y)) for _,x,y in hist.as_list()]
                for a,b in zip(pts,pts[1:]):cv2.line(out,a,b,(255,170,0),2)
                pred=self.predictor.predict(hist)
                for a,b in zip(pts[-1:],[(int(x),int(y)) for _,x,y in pred]):cv2.line(out,a,b,(0,180,255),2)
        return self._jpeg(out)
    def _jpeg(self,image):
        if isinstance(image,bytes): return image
        import cv2
        ok,data=cv2.imencode('.jpg',image); return data.tobytes() if ok else b''
    def status(self):
        def hz(ts): return (len(ts)-1)/(ts[-1]-ts[0]) if len(ts)>1 and ts[-1]>ts[0] else 0.0
        cutoff=time.time()-self.display_history_seconds
        people=[{'name':x['name'],'person_id':x['person_id'],'track_id':i,'confidence':x['confidence'],'zone':x['zone'],'visible_seconds':x['work'].seconds(x['person_id'],'visible') if x['person_id'] else 0.0,'history':[p for p in x['history'].as_list() if p[0]>=cutoff],'predictions':self.predictor.predict(x['history'])} for i,x in self.people.items() if not self.confirmed_only or getattr(self.tracker.tracks.get(i),'state',None)=='CONFIRMED']
        tracker_diag=self.tracker.diagnostics() if hasattr(self.tracker,'diagnostics') else {}
        return {'camera_fps':hz(self.camera_times),'ai_fps':hz(self.ai_times),'detection_fps':1000/sum(self.detector_times)/len(self.detector_times) if self.detector_times and sum(self.detector_times)>0 else 0.0,'face_fps':len(self.face_times)/sum(self.face_times) if self.face_times and sum(self.face_times)>0 else 0.0,'latency_ms':self.latency_ms,'queue_size':self.queue_size,'dropped_frames':self.dropped_frames,'input':self.source_stats,'detector_device':getattr(self.detector,'actual_device',getattr(self.detector,'device',None)),'detector_diagnostics':getattr(self.detector,'last_diagnostics',None),'tracker_diagnostics':tracker_diag,'tracker_type':getattr(self.tracker,'tracker_type','simple'),'tracker_backend':getattr(self.tracker,'backend_name','local.simple_iou'),'insightface_provider':getattr(self.recognizer,'provider',None),'face_diagnostics':getattr(self.recognizer,'last_diagnostics',None),'face_database':getattr(getattr(self.recognizer,'database',None),'last_scan',None),'people':people}
    def close(self, timestamp=None):
        if self.face_executor:
            self.face_executor.shutdown(wait=True,cancel_futures=False); self._drain_face_results()
        if not self.writer:return
        timestamp=time.time() if timestamp is None else timestamp
        self.writer.flush()
        for track_id,person in self.people.items():
            for person_id,session in person['work'].sessions.items():
                self.writer.database.add_session(person_id,track_id,session['start'],session['last_seen'],session['max_gap'])
                self.writer.database.add_daily_stat(time.strftime('%Y-%m-%d',time.localtime(session['start'])),person_id,'visible',person['work'].seconds(person_id,'visible'))
                for zone,seconds in session['zones'].items():self.writer.database.add_daily_stat(time.strftime('%Y-%m-%d',time.localtime(session['start'])),person_id,zone,seconds)
        self.writer.database.commit()

async def run_app(a):
    from aiohttp import web
    cfg=load_config(a.config)
    runtime_cfg=cfg.get('runtime',{})
    if runtime_cfg.get('require_gpu', True):
        # Fail at startup with the full CUDA/PATH traceback; never silently use CPU.
        diagnose()
    recognizer=None
    face_cfg=cfg.get('face',{})
    try:
        db=FaceDatabase('data/persons'); db.scan();
        if db.records and face_cfg.get('enabled',True): recognizer=FaceRecognizer(db,threshold=face_cfg.get('recognition_threshold',.45),det_size=face_cfg.get('det_size',[1280,1280]),min_face_size=face_cfg.get('min_face_size',24),min_det_score=face_cfg.get('min_det_score',.5))
    except Exception:
        traceback.print_exc()
        raise
    database=AnalyticsDatabase(cfg.get('database',{}).get('path','runtime/person_analytics.db')); writer=BatchWriter(database); writer.thread.start()
    detector_cfg=cfg.get('detector',{}); profile=detector_cfg.get('profiles',{}).get(detector_cfg.get('profile',''),{}); model=profile.get('model',detector_cfg.get('model',a.model)); confidence=detector_cfg.get('confidence',.5); inference_size=profile.get('inference_size',detector_cfg.get('inference_size',640)); tracker_cfg=cfg.get('tracker',{}); trajectory_cfg=cfg.get('trajectory',{}); session_cfg=cfg.get('session',{})
    tracker_type=tracker_cfg.get('type','bytetrack').lower()
    try:
        tracker=UltralyticsTracker(tracker_type=tracker_type,track_buffer=tracker_cfg.get('track_buffer',30),frame_rate=tracker_cfg.get('frame_rate',20),high_thresh=tracker_cfg.get('track_high_thresh',.25),low_thresh=tracker_cfg.get('track_low_thresh',.1),new_track_thresh=tracker_cfg.get('new_track_thresh',.25),match_thresh=tracker_cfg.get('match_thresh',.8),fuse_score=tracker_cfg.get('fuse_score',True))
    except Exception:
        if tracker_cfg.get('allow_simple_fallback',False):
            traceback.print_exc(); tracker=None
        else: raise
    zones=[]
    for zone_id,zone_cfg in cfg.get('zones',{}).items():
        polygon=tuple(tuple(p) for p in zone_cfg.get('polygon',[]))
        if len(polygon)>=3: zones.append(Zone(zone_id,zone_cfg.get('name',zone_id),polygon))
    app=AnalyticsApp(a.source,PersonDetector(model,confidence,device=runtime_cfg.get('device','cuda:0'),inference_size=inference_size,adaptive=detector_cfg.get('adaptive',{})),recognizer,writer,zones,face_cfg.get('check_interval_unknown',.5),face_cfg.get('check_interval_known',3.0),tracker_cfg.get('track_buffer',30),trajectory_cfg.get('storage_history_seconds',trajectory_cfg.get('history_seconds',30)),trajectory_cfg.get('prediction_steps'),trajectory_cfg.get('minimum_movement_pixels',2.0),session_cfg.get('grace_seconds',5.0),runtime_cfg.get('inference_max_width',1920),tracker_cfg.get('confirmed_only',True),tracker_cfg.get('confirm_hits',2),tracker_cfg.get('weak_confirm_hits',4),tracker_cfg.get('weak_confidence',.30),tracker=tracker,display_history_seconds=trajectory_cfg.get('display_history_seconds',8),smoothing_alpha=trajectory_cfg.get('smoothing_alpha',.35))
    async def index(_):
        zone_data=[{'name':z.name,'polygon':z.polygon} for z in zones]
        page=HTML.replace('<script>async function tick()', '<script>const m=document.getElementById("m"),v=document.getElementById("v"),p=document.getElementById("p"),d=document.getElementById("d");const zones='+json.dumps(zone_data,ensure_ascii=False)+';async function tick()')
        page=page.replace('c.drawImage(im,0,0);', "c.drawImage(im,0,0);zones.forEach(z=>{c.strokeStyle='#ffdd00';c.lineWidth=3;c.beginPath();z.polygon.forEach((q,i)=>i?c.lineTo(q[0],q[1]):c.moveTo(q[0],q[1]));c.closePath();c.stroke();c.fillStyle='#ffdd00';c.font='20px sans-serif';c.fillText(z.name,z.polygon[0][0],z.polygon[0][1]);});")
        page=page.replace('Camera FPS ${s.camera_fps.toFixed(1)} | AI FPS ${s.ai_fps.toFixed(1)} | latency ${s.latency_ms.toFixed(1)}ms', 'Camera FPS ${s.camera_fps.toFixed(1)} | AI FPS ${s.ai_fps.toFixed(1)} | Face FPS ${s.face_fps.toFixed(1)} | latency ${s.latency_ms.toFixed(1)}ms | dropped ${s.dropped_frames} | input ${s.input.healthy ? "live" : "waiting"}${s.input.last_error ? " ("+s.input.last_error+")" : ""}')
        page=page.replace('async function tick(){', 'let busy=false;async function tick(){if(busy)return;busy=true;try{')
        page=page.replace('}setInterval(tick,500);tick()', '}finally{busy=false}}setInterval(tick,100);tick()')
        name_token='$'+'{x.name}'
        page=page.replace('<td>'+name_token+'</td>', "<td><a href='/analytics/person/"+'$'+"{encodeURIComponent(x.person_id||'')}'>"+name_token+"</a></td>")
        return web.Response(text=page,content_type='text/html')
    async def status(_): return web.json_response(app.status())
    async def frame(_):
        if not app.last_frame:
            raise web.HTTPServiceUnavailable(text='Waiting for a current Gateway frame')
        return web.Response(body=app.last_frame,content_type='image/jpeg',headers={'Cache-Control':'no-store'})
    async def today(_):
        day=time.strftime('%Y-%m-%d'); rows=database.db.execute('SELECT person_id,metric,seconds FROM daily_statistics WHERE day=? ORDER BY person_id,metric',(day,)).fetchall()
        return web.json_response([{'person_id':p,'metric':m,'seconds':s} for p,m,s in rows])
    async def person_api(request):
        person_id=request.match_info['person_id']; rows=database.db.execute('SELECT timestamp,track_id,x_image,y_image,zone FROM trajectory_points WHERE person_id=? ORDER BY timestamp DESC LIMIT 1000',(person_id,)).fetchall(); stats=database.db.execute('SELECT metric,seconds FROM daily_statistics WHERE person_id=? ORDER BY metric',(person_id,)).fetchall()
        name_row=database.db.execute('SELECT name FROM persons WHERE id=?',(person_id,)).fetchone(); first=database.db.execute('SELECT MIN(timestamp) FROM trajectory_points WHERE person_id=?',(person_id,)).fetchone()[0]; last=database.db.execute('SELECT MAX(timestamp) FROM trajectory_points WHERE person_id=?',(person_id,)).fetchone()[0]
        avatar=None; person_dir=Path('data/persons')/person_id
        if person_dir.is_dir():
            files=sorted(x for x in person_dir.iterdir() if x.suffix.lower() in {'.jpg','.jpeg','.png'})
            if files: avatar='/analytics/person/'+person_id+'/avatar'
        return web.json_response({'person_id':person_id,'name':name_row[0] if name_row else person_id,'avatar':avatar,'first_seen':first,'last_seen':last,'statistics':[{'metric':m,'seconds':s} for m,s in stats],'trajectory':[{'timestamp':t,'track_id':i,'x':x,'y':y,'zone':z} for t,i,x,y,z in reversed(rows)]})
    async def person_page(request):
        person_id=request.match_info['person_id']; safe=json.dumps(person_id,ensure_ascii=False)
        html='''<!doctype html><meta charset="utf-8"><title>人员详情</title><style>body{background:#101820;color:#eee;font:16px sans-serif;margin:2em}img{max-width:180px;max-height:180px}a{color:#7cf}</style><a href="/analytics">← 返回实时分析</a><h1 id="name">人员详情</h1><img id="avatar"><pre id="summary">加载中</pre><h2>轨迹点</h2><pre id="traj"></pre><script>const id=__ID__;fetch('/api/analytics/person/'+encodeURIComponent(id)).then(r=>r.json()).then(x=>{name.textContent=x.name+' ('+x.person_id+')';if(x.avatar)avatar.src=x.avatar;summary.textContent=JSON.stringify({first_seen:x.first_seen,last_seen:x.last_seen,statistics:x.statistics},null,2);traj.textContent=JSON.stringify(x.trajectory,null,2)})</script>'''.replace('__ID__',safe)
        return web.Response(text=html,content_type='text/html')
    async def avatar(request):
        person_id=request.match_info['person_id']; folder=(Path('data/persons')/person_id).resolve(); root=Path('data/persons').resolve()
        if root not in folder.parents: raise web.HTTPNotFound()
        files=sorted(x for x in folder.iterdir() if x.suffix.lower() in {'.jpg','.jpeg','.png'}) if folder.is_dir() else []
        if not files: raise web.HTTPNotFound()
        return web.FileResponse(files[0])
    server=web.Application(); server.router.add_get('/analytics',index); server.router.add_get('/analytics/person/{person_id}',person_page); server.router.add_get('/analytics/person/{person_id}/avatar',avatar); server.router.add_get('/api/analytics/person/{person_id}',person_api); server.router.add_get('/api/analytics',status); server.router.add_get('/api/analytics/today',today); server.router.add_get('/frame.jpg',frame)
    runner=web.AppRunner(server); await runner.setup(); await web.TCPSite(runner,'127.0.0.1',a.http_port).start()
    def consume():
        import cv2
        if a.source=='video':
            cap=cv2.VideoCapture(a.video)
            fps=cap.get(cv2.CAP_PROP_FPS) or 10.0; media_start=time.time(); frame_index=0
            while True:
                ok,frame=cap.read()
                if not ok:break
                app.process(frame,media_start + frame_index / fps); frame_index += 1
            cap.release()
        elif a.source=='image-dir':
            import numpy as np
            media_start=time.time()
            for frame_index,f in enumerate(sorted(Path(a.image_dir).glob('*'))):
                frame=cv2.imdecode(np.fromfile(str(f),dtype=np.uint8),cv2.IMREAD_COLOR)
                if frame is not None:app.process(frame,media_start + frame_index / 10.0)
        else:
            from queue import Empty
            from .capture import GatewayFrameSource
            gateway=GatewayFrameSource(a.gateway_url,cfg.get('camera',{}).get('queue_size',2)).start()
            try:
                while True:
                    try: packet=gateway.get(1.0)
                    except Empty:
                        app.set_source_stats(**gateway.stats())
                        continue
                    stats=gateway.stats(); app.set_source_stats(**stats); app.process(packet.payload,packet.received_wall_ns/1e9)
            finally: gateway.close()
        if a.source in ('video','image-dir'):
            while True: time.sleep(1)
    try: await asyncio.to_thread(consume)
    finally:
        app.close()
        writer.stop.set(); writer.thread.join(3); database.close(); await runner.cleanup()

def main():
    p=argparse.ArgumentParser(); p.add_argument('--source',choices=['gateway','video','image-dir']); p.add_argument('--video'); p.add_argument('--image-dir'); p.add_argument('--gateway-url',default='http://127.0.0.1:8080/latest.jpg'); p.add_argument('--http-port',type=int,default=8090); p.add_argument('--model',default='models/yolo11n.pt'); p.add_argument('--config',default='config/person_analytics.yaml'); a=p.parse_args()
    if not a.source:a.source='video' if a.video else ('image-dir' if a.image_dir else 'gateway')
    try:
        asyncio.run(run_app(a))
    except KeyboardInterrupt: pass
    except ImportError as exc: raise SystemExit('Install AI runtime dependencies (opencv-python, ultralytics): '+str(exc))

if __name__=='__main__':main()
