# 人员分析测试报告

当前离线验证（`.venv_ai` Python 3.11.9）：

```text
104 tests passed
```

覆盖 Gateway 原有测试、分析有界帧队列、不可变帧、IoU 跟踪 ID 稳定、恒速预测、Unknown/已知身份时间融合与 track 合并、ROI polygon、时间戳工时和 SQLite 轨迹写入。

GPU 重新核查（2026-09-03）：GPU 为 NVIDIA GeForce RTX 4060 Laptop GPU、8188 MiB；Driver 591.86；`nvidia-smi` 显示 CUDA 13.1。`.venv_ai` 使用 Python 3.11.9、`onnxruntime-gpu` 1.29.0（CPU 包不存在），可用 provider 为 TensorRT/CUDA/CPU；InsightFace buffalo_l 的所有模型 session 均实际报告 `CUDAExecutionProvider` 在首位。YOLO 使用 PyTorch 2.14.0+cu130，`cuda:0`。真实 warm benchmark：YOLO 平均 15.58 ms；InsightFace 人脸检测+embedding 平均 26.57 ms；ArcFace embedding 平均 4.06 ms。并发 `nvidia-smi` 采样观察到 Python 推理期间显存约升至 1095 MiB、GPU 利用率最高约 67%。照片库实际结果为 61 人、61 张有效人脸；未替换现有 Gateway。

真实 Gateway 短测：Gateway `/api/status` healthy=true、JPEG 1920x1080、约 10 Hz；分析端独立读取 `/latest.jpg`，Web API 可返回真实 bbox/track/history/predictions。此前 0.18–0.20 FPS、约 3.9 s 延迟是 CPU 环境数据，不能作为当前 GPU 结果；需要用当前 GPU 环境重新跑生产流验收。

此前“没有 CUDA”的判断是错误的：把默认系统 Python/CPU AI 包的 provider 结果误当成了物理机器能力，而且没有先执行 `nvidia-smi`。准确结论是“RTX 4060 与驱动正常，旧 `.venv_ai` 使用 CPU-only ONNX Runtime 和 CPU-only PyTorch”，不是“机器没有 CUDA”。
