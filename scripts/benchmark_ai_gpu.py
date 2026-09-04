"""Repeatable warm benchmark for YOLO, InsightFace detection, and ArcFace."""
import argparse, json, time
from pathlib import Path
import cv2, numpy as np
import onnxruntime as ort
ort.preload_dlls()
import torch
from ultralytics import YOLO
from insightface.app import FaceAnalysis


def bench(fn, count):
    values=[]
    for _ in range(count):
        start=time.perf_counter(); fn()
        if torch.cuda.is_available(): torch.cuda.synchronize()
        values.append((time.perf_counter()-start)*1000)
    return {'avg_ms':sum(values)/len(values),'min_ms':min(values),'max_ms':max(values)}


def main():
    p=argparse.ArgumentParser(); p.add_argument('image'); p.add_argument('--model',default='models/yolo11n.pt'); p.add_argument('--runs',type=int,default=20); p.add_argument('--sizes',default='640,960,1280'); p.add_argument('--face-det-size',type=int,default=1280); a=p.parse_args()
    image=cv2.imdecode(np.fromfile(str(Path(a.image)),dtype=np.uint8),cv2.IMREAD_COLOR)
    if image is None: raise SystemExit(f'cannot decode image: {a.image}')
    yolo=YOLO(a.model); yolo_results={}
    for size in (int(value) for value in a.sizes.split(',') if value.strip()):
        yolo.predict(image,device='cuda:0',imgsz=size,classes=[0],verbose=False)
        yolo_results[str(size)]=bench(lambda size=size:yolo.predict(image,device='cuda:0',imgsz=size,classes=[0],verbose=False),a.runs)
    face=FaceAnalysis(name='buffalo_l',providers=['CUDAExecutionProvider']); face.prepare(ctx_id=0,det_size=(a.face_det_size,a.face_det_size)); faces=face.get(image)
    face_result=bench(lambda:face.get(image),max(5,a.runs//2))
    recognition=face.models['recognition']; sample=np.zeros((1,3,112,112),np.float32); input_name=recognition.session.get_inputs()[0].name; recognition.session.run(None,{input_name:sample})
    arc_result=bench(lambda:recognition.session.run(None,{input_name:sample}),a.runs)
    print(json.dumps({'onnxruntime':ort.__version__,'providers':ort.get_available_providers(),'torch':torch.__version__,'gpu':torch.cuda.get_device_name(0),'gpu_memory_mb':round(torch.cuda.memory_allocated()/1024/1024,1),'gpu_memory_reserved_mb':round(torch.cuda.memory_reserved()/1024/1024,1),'face_count':len(faces),'yolo':yolo_results,'face_detection':face_result,'arcface':arc_result,'insightface_providers':{k:v.session.get_providers() for k,v in face.models.items()}},ensure_ascii=False,indent=2))


if __name__=='__main__': main()
