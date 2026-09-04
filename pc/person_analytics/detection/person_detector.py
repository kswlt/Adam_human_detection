import time


class PersonDetector:
    """Ultralytics adapter. Import is lazy so Gateway and offline tests need no AI packages."""
    def __init__(self,model='models/yolo11n.pt',confidence=.5,device=None,inference_size=640,
                 adaptive=None):
        self.model_path=model; self.confidence=confidence; self.device=device; self.inference_size=inference_size; self.model=None
        self.adaptive=adaptive or {}
        self._last_secondary=0.0
        self.last_diagnostics={'primary_count':0,'secondary_ran':False,'secondary_count':0}
    def load(self):
        from ultralytics import YOLO
        from ..gpu import require_torch_cuda
        torch = require_torch_cuda()
        self.device = self.device or 'cuda:0'
        self.model=YOLO(self.model_path)
        self.actual_device = self.device
        torch.cuda.get_device_name(0)
        return self
    def _predict(self, image, confidence, inference_size):
        if self.model is None:self.load()
        result=self.model.predict(image,conf=confidence,imgsz=inference_size,device=self.device,classes=[0],verbose=False)[0]
        Detection=__import__('pc.person_analytics.tracking',fromlist=['Detection']).Detection
        return [Detection(tuple(map(float,b)),float(c),int(k)) for b,c,k in zip(result.boxes.xyxy.cpu().tolist(),result.boxes.conf.cpu().tolist(),result.boxes.cls.cpu().tolist()) if int(k)==0]

    @staticmethod
    def _merge(primary, secondary, iou_threshold=.55):
        """Keep the stronger box when the two passes found the same person."""
        from ..tracking.tracker import iou
        merged=sorted(primary + secondary,key=lambda d:d.confidence,reverse=True)
        kept=[]
        for detection in merged:
            if all(iou(detection.bbox,other.bbox) < iou_threshold for other in kept):
                kept.append(detection)
        return kept

    def detect(self,image):
        primary=self._predict(image,self.confidence,self.inference_size)
        cfg=self.adaptive
        enabled=bool(cfg.get('enabled',False))
        trigger_count=int(cfg.get('trigger_person_count',1))
        trigger_confidence=float(cfg.get('trigger_max_confidence',.55))
        strongest=max((item.confidence for item in primary),default=0.0)
        should_run=enabled and (len(primary)<=trigger_count or strongest<trigger_confidence)
        now=time.monotonic()
        interval=float(cfg.get('min_interval_seconds',.5))
        secondary=[]
        secondary_ran=False
        if should_run and now-self._last_secondary>=interval:
            self._last_secondary=now
            secondary_ran=True
            secondary=self._predict(image,float(cfg.get('secondary_confidence',.15)),int(cfg.get('secondary_inference_size',960)))
        self.last_diagnostics={
            'primary_count':len(primary), 'primary_max_confidence':strongest,
            'secondary_ran':secondary_ran,
            'secondary_count':len(secondary), 'secondary_inference_size':cfg.get('secondary_inference_size',960),
        }
        return self._merge(primary,secondary,float(cfg.get('nms_iou',.55))) if secondary else primary
