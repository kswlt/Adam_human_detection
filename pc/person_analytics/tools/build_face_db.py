import argparse
from pc.person_analytics.face.face_database import FaceDatabase
def main():
    p=argparse.ArgumentParser(); p.add_argument('--rebuild',action='store_true'); p.add_argument('--root',default='data/persons'); a=p.parse_args()
    embedder=None
    try:
        import cv2
        from insightface.app import FaceAnalysis
        from pc.person_analytics.gpu import require_onnx_cuda
        require_onnx_cuda()
        model=FaceAnalysis(name='buffalo_l',providers=['CUDAExecutionProvider']); model.prepare(ctx_id=0,det_size=(1280,1280))
        import numpy as np
        def embed(path):
            image=cv2.imdecode(np.fromfile(str(path),dtype=np.uint8),cv2.IMREAD_COLOR)
            faces=model.get(image)
            if not faces: raise ValueError('no face detected')
            return faces[0].normed_embedding.tolist()
        embedder=embed
    except Exception as exc:
        print(f'人脸模型/CUDA 不可用，停止构建，完整错误: {exc}')
        raise
    result=FaceDatabase(a.root).scan(embedder=embedder,rebuild=a.rebuild)
    print(f"总人员数: {result['persons']}\n总有效人脸: {result['valid_faces']}")
    for item in result['invalid']:print(f"无法处理: {item['person']} {item['image']}: {item['error']}")
if __name__=='__main__':main()
