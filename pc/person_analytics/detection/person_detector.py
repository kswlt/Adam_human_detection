class PersonDetector:
    """Ultralytics adapter. Import is lazy so Gateway and offline tests need no AI packages."""
    def __init__(self,model='models/yolo11n.pt',confidence=.5,device=None,inference_size=640):
        self.model_path=model; self.confidence=confidence; self.device=device; self.inference_size=inference_size; self.model=None
    def load(self):
        from ultralytics import YOLO
        from ..gpu import require_torch_cuda
        torch = require_torch_cuda()
        self.device = self.device or 'cuda:0'
        self.model=YOLO(self.model_path)
        self.actual_device = self.device
        torch.cuda.get_device_name(0)
        return self
    def detect(self,image):
        if self.model is None:self.load()
        result=self.model.predict(image,conf=self.confidence,imgsz=self.inference_size,device=self.device,verbose=False)[0]
        return [__import__('pc.person_analytics.tracking',fromlist=['Detection']).Detection(tuple(map(float,b)),float(c),int(k)) for b,c,k in zip(result.boxes.xyxy.cpu().tolist(),result.boxes.conf.cpu().tolist(),result.boxes.cls.cpu().tolist()) if int(k)==0]
