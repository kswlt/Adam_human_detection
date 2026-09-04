# 人员分析安装

生产网关环境与 AI 环境分离。先保持现有 `setup_pc.ps1` 和 `.venv` 不变，在 Windows PowerShell 执行：

```powershell
.\setup_person_analytics.ps1
```

该脚本使用 Python 3.11 创建 `.venv_ai`，安装 OpenCV、Ultralytics、CUDA 版 PyTorch、`onnxruntime-gpu` 1.29、InsightFace、PyYAML 和 aiohttp。当前配置为 GPU fail-fast：CUDA provider 加载失败会输出完整错误，不会静默回退 CPU。模型大文件不进入 Git；首次加载时按上游许可下载，生产部署前请记录模型版本与 SHA256。

重复执行 GPU 环境诊断：

```powershell
.\scripts\diagnose_gpu.ps1
```

重复执行模型 benchmark：

```powershell
.\.venv_ai\Scripts\python.exe scripts\benchmark_ai_gpu.py data\persons\于子晴\001.jpg
```

照片库放在 `data/persons/<姓名>/*.jpg`，然后执行：

```powershell
.\.venv_ai\Scripts\python.exe -m pc.person_analytics.tools.build_face_db
```
