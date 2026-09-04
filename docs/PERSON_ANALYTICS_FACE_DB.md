# 人脸库

每个姓名对应一个目录，可包含多张 JPG/PNG。索引保存照片 SHA256 与 embedding，照片未变化时不会重复计算；坏图或未检测到人脸会单独报告，其他人员继续处理。embedding 和照片均只写本地 `data/face_db` 与 `data/persons`。

当前 embedding 提取由 InsightFace `FaceAnalysis` 适配器负责，识别使用余弦相似度和配置阈值；若 AI 依赖或模型缺失，Gateway 不受影响，分析进程报告 degraded。

