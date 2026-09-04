class FaceRecognizer:
    """Optional InsightFace adapter; returns (person_id, cosine-like score) candidates."""
    def __init__(self, database, threshold=.45, det_size=(1280,1280), min_face_size=24, min_det_score=.5):
        self.database=database; self.threshold=threshold; self.det_size=tuple(det_size); self.min_face_size=float(min_face_size); self.min_det_score=float(min_det_score); self.app=None; self.provider='not_loaded'; self.last_diagnostics={'faces':0,'best_person':None,'best_score':0.0}
    def load(self):
        from insightface.app import FaceAnalysis
        from ..gpu import require_onnx_cuda
        require_onnx_cuda()
        self.app=FaceAnalysis(name='buffalo_l',providers=['CUDAExecutionProvider']); self.app.prepare(ctx_id=0,det_size=self.det_size)
        model_providers={name: model.session.get_providers() for name,model in self.app.models.items()}
        if any('CUDAExecutionProvider' not in providers for providers in model_providers.values()):
            raise RuntimeError(f'InsightFace CUDA provider not active: {model_providers}')
        self.provider='CUDAExecutionProvider'
        self.model_providers=model_providers
        return self
    def recognize(self,image,bbox=None):
        if self.app is None:self.load()
        original=image; expanded=None
        if bbox is not None:
            x1,y1,x2,y2=map(int,bbox); h,w=image.shape[:2]; pad_x=int((x2-x1)*.15); pad_y=int((y2-y1)*.15)
            expanded=(max(0,x1-pad_x),max(0,y1-pad_y),min(w,x2+pad_x),min(h,y2+pad_y))
            image=image[expanded[1]:expanded[3],expanded[0]:expanded[2]]
            # Distant people occupy very few pixels in a 4K frame. Upscale the
            # ROI before detection so the face detector gets usable detail.
            if min(image.shape[:2]) < 600:
                import cv2
                image=cv2.resize(image,None,fx=2.0,fy=2.0,interpolation=cv2.INTER_CUBIC)
        faces=self.app.get(image)
        if not faces and bbox is not None:
            # A detector box can include a large body or clip a face at its edge.
            # Retry on the original 4K frame, then keep only faces belonging to it.
            ox1,oy1,ox2,oy2=expanded
            faces=[f for f in self.app.get(original) if ox1 <= (f.bbox[0]+f.bbox[2])/2 <= ox2 and oy1 <= (f.bbox[1]+f.bbox[3])/2 <= oy1+(oy2-oy1)*.72]
        quality=[]
        valid=[]
        for face in faces:
            fx1,fy1,fx2,fy2=map(float,face.bbox); size=min(fx2-fx1,fy2-fy1); score=float(getattr(face,'det_score',1.0))
            item={'size':round(size,2),'det_score':round(score,4)}; quality.append(item)
            if size >= self.min_face_size and score >= self.min_det_score: valid.append(face)
        faces=valid
        if not faces:
            self.last_diagnostics={'faces':0,'raw_faces':len(quality),'quality':quality,'best_person':None,'best_score':0.0}; return []
        result=[]
        best_person=None; best_score=0.0
        for face in faces:
            emb=face.normed_embedding
            for person,record in self.database.records.items():
                vectors=record.get('embeddings',[])+([record['centroid']] if record.get('centroid') else [])
                score=max(float(emb @ vector) for vector in vectors)
                if score>best_score: best_person,best_score=person,score
                if score>=self.threshold:result.append((person,score))
        self.last_diagnostics={'faces':len(faces),'raw_faces':len(quality),'quality':quality,'best_person':best_person,'best_score':best_score,'threshold':self.threshold}
        return sorted(result,key=lambda x:x[1],reverse=True)
