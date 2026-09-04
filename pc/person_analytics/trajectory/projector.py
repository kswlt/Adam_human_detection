class HomographyProjector:
    def __init__(self,image_points=None,world_points=None):
        self.image_points=image_points or []; self.world_points=world_points or []
        if len(self.image_points)!=len(self.world_points) or len(self.image_points)<4: self.matrix=None
        else:
            try:
                import cv2, numpy as np
                self.matrix,_=cv2.findHomography(np.asarray(self.image_points,float),np.asarray(self.world_points,float))
            except ImportError:self.matrix=None
    @property
    def mode(self): return 'ground' if self.matrix is not None else 'image'
    def project(self,point):
        if self.matrix is None:return (float(point[0]),float(point[1]))
        import cv2, numpy as np
        out=cv2.perspectiveTransform(np.asarray([[point]],float),self.matrix)[0][0]; return (float(out[0]),float(out[1]))

