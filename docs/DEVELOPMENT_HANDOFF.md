# Adam_human_detection 开发交接文档

最后更新：2026-09-04

## 1. 项目定位

本仓库来自 `kswlt/yk`，当前 GitHub 目标仓库为 `kswlt/Adam_human_detection`。项目原始目标是“云科空间相机协议网关”：板端 RK3562/空间相机/雷达通过 Zenoh 发布数据，Windows PC 网关转为 HTTP 和 Foxglove 可视化。

本阶段在原网关旁路增加了 PC 人员分析系统：

```text
相机 H264/JPEG -> 原有 Gateway :8080 -> latest.jpg
                                      |
                                      v
                         pc.person_analytics :8090
                         YOLO 人员检测/跟踪
                         InsightFace + ArcFace 人脸识别
                         SQLite 轨迹、区域、工作时长
```

人员分析不会替换或修改 Gateway 的协议语义；它通过 `http://127.0.0.1:8080/latest.jpg` 读取最新画面。

## 2. 开发现场

- 操作系统：Windows，PowerShell。
- 当前 AI 工作目录：`C:\Users\Admin\Desktop\人员识别\yk`。
- 原 Gateway 工作目录：`C:\Users\Admin\Desktop\yunke`，由原项目的 `YunKeAutostart` 守护。
- AI 独立虚拟环境：`yk\.venv_ai`。不要和原 Gateway 的 `.venv` 混用，也不要修改原 Gateway Python 环境。
- AI 页面：`http://127.0.0.1:8090/analytics`。
- Gateway 页面：`http://127.0.0.1:8080/`。
- Gateway 状态：`http://127.0.0.1:8080/api/status`。
- AI 状态：`http://127.0.0.1:8090/api/analytics`。

## 3. 当前输入与 GPU 状态

现场相机已切换为原生 H264，约 3840×2160、20 FPS。Gateway 会将 H264 解码为 JPEG 供浏览器和 AI 读取；AI 不把 4K 画面整体缩小后做人脸识别：

- YOLO 为实时性使用配置的检测输入（当前 1920 宽、640 检测尺寸）。
- 人脸识别使用 4K 原图和对应的人体 ROI。
- 小 ROI（小于 600 像素）会自动放大 2 倍后送入 InsightFace。
- InsightFace 人脸检测尺寸已改为 `1280×1280`，原 640 会漏掉远处小脸。

当前已实际确认：同一张 4K 画面的人脸检测在 640 时检测不到，在 1280 时检测到 3 张，在 1600 时检测到 5 张。

GPU 运行链路已验证：

- YOLO 实际设备：`cuda:0`。
- InsightFace 实际 provider：`CUDAExecutionProvider`。
- ONNX Runtime 会在服务启动时严格检查 CUDA provider，禁止静默回退 CPU。
- 最近服务状态示例：AI FPS 约 14.3，检测 FPS 约 47.9，Face FPS 约 3.6，延迟约 82 ms；实际数值随画面和 Gateway 输入变化。

## 4. 已完成的主要开发内容

### 人员分析

- `pc/person_analytics/app.py`：Gateway/视频/图片目录输入、异步分析循环、实时网页、指标接口。
- `pc/person_analytics/detection/person_detector.py`：Ultralytics YOLO GPU 人员检测，只接收 class 0 `person`。
- `pc/person_analytics/tracking/`：ByteTrack 风格跟踪、轨迹历史、速度预测。
- `pc/person_analytics/face/recognizer.py`：InsightFace/ArcFace CUDA 推理、4K ROI、全图回退、小 ROI 放大、匹配分数诊断。
- `pc/person_analytics/face/identity.py`：多次观察确认身份，避免一次低质量人脸直接改名。
- `pc/person_analytics/storage/`：SQLite 批量写入人员、轨迹、区域和工作时长。
- 前端轮询已经从 500 ms 调整到 100 ms，并增加 busy 防重入，避免必须手动刷新才更新。

### GPU/运行环境

- `pc/person_analytics/gpu.py`：严格检查 NVIDIA、PyTorch CUDA、ONNX Runtime CUDA provider。
- `requirements-ai.txt`：独立 AI 依赖，使用 `onnxruntime-gpu`，不覆盖 Gateway 环境。
- `scripts/diagnose_gpu.ps1`：GPU/CUDA/ORT 诊断。
- `scripts/benchmark_ai_gpu.py`：GPU benchmark 入口。
- `setup_person_analytics.ps1`：创建 `.venv_ai` 并安装 AI 依赖。

### 当前识别策略调整

- 人脸识别阈值：`0.45`。低于该分数显示 `Unknown`，不强行显示错误姓名。
- YOLO 人体阈值：当前配置为 `0.35`，用于保留远处/遮挡人员；此前 `0.60` 会漏掉部分低置信度真人。
- 空椅子误检仍需进一步使用连续轨迹、静态目标和人脸证据做二次过滤，不能简单再次提高人体阈值，否则会重新漏掉远处人员。

### 2026-09-04 重构进展

- 生产默认 tracker 已从自写 `SimpleByteTracker` 切换为当前环境 Ultralytics 8.4.138 的官方 `BYTETracker`，实际状态接口显示 `tracker_backend=ultralytics.bytetrack`。
- `track_buffer` 按明确的 `frame_rate` 解释，短时漏检可由官方 tracker 的 lost/refind 逻辑恢复原 ID；自写 tracker 仍保留给离线兼容测试。
- YOLO 推理层已传递 `classes=[0]`，减少无关 COCO 类别处理。
- 轨迹历史增加 raw 点和 EMA 平滑点；生产业务默认使用平滑点，预测不再使用原始抖动点。
- 后端 `/frame.jpg` 返回原始 JPEG，网页 Canvas 作为唯一 overlay renderer，避免后端和前端重复绘框。
- UI/API 默认只展示最近约 8 秒轨迹；数据库保存更长的存储历史。
- 已新增官方 tracker 短时漏检恢复测试；当前全仓库 107 个 unittest 测试通过。
- Windows 实机 benchmark 已执行当前 `yolo11n.pt`：YOLO 640/960/1280、InsightFace detection 和 ArcFace embedding。`yolo11s`/`yolo11m` 权重当前未下载，因此 balanced/quality 组合尚未伪造结果。

## 5. 运行方法

首次安装：

```powershell
cd C:\Users\Admin\Desktop\人员识别\yk
.\setup_person_analytics.ps1
```

启动 AI：

```powershell
.\start_person_analytics.ps1
```

访问：

```text
http://127.0.0.1:8090/analytics
```

如果 8090 已被旧进程占用，先只结束监听 8090 的旧 AI 进程，再启动当前 `.venv_ai` 服务；不要结束 8080 的生产 Gateway，除非明确要重启 Gateway。

## 6. 人脸库

人脸原图位于 `data/persons/<姓名>/`，属于现场隐私数据，已加入 `.gitignore`，不会上传 GitHub。人脸 embedding/index 也不上传。新环境需要由现场管理员重新放入照片并构建数据库，详见：

- [人员库说明](PERSON_ANALYTICS_FACE_DB.md)
- `pc/person_analytics/tools/build_face_db.py`

同一个人在当前摄像机角度、侧脸、低头、远距离条件下建议提供多张样本。相似度约 0.11 不是阈值问题，而是有效人脸像素太少或样本差异过大，不能直接把阈值降到该水平。

## 7. 最近现场现象与判定

### 页面空白、FPS 全为 0

先查 Gateway：

```powershell
(Invoke-WebRequest http://127.0.0.1:8080/api/status -UseBasicParsing).Content
```

如果 `image.age_seconds` 很大、`hz=0`、`healthy=false`，或 `/latest.jpg` 返回 503，说明相机/Gateway 没有新帧；AI 服务本身可能正常但没有输入。

### 空椅子被框选

这是 YOLO 将椅背误判成 `person`，不是人脸识别把椅子认成某个人。当前改为只接收 person 类，并将阈值调整为 0.35 以避免漏检远处真人。后续应增加目标确认策略，而不是降低人脸识别阈值。

### 画面里有人但没有姓名

人体检测和身份识别是两层：YOLO 检测到人不等于人脸质量足以匹配。查看 `/api/analytics` 中的 `face_diagnostics`：

- `faces=0`：人脸检测阶段没有得到有效脸，常见原因是遮挡、侧脸或像素太小。
- `faces>0` 但 `best_score < 0.45`：检测到了脸，但没有可靠匹配；应补充对应角度的人脸样本。
- `insightface_provider` 必须为 `CUDAExecutionProvider`。

## 8. 目前未完成/下一步

1. 在真实 4K/20 FPS 长时间运行下，继续测量远距离小目标召回率和 GPU 显存。
2. 增加“静态椅子/物体”过滤：结合连续帧稳定性、人体框形态、人体关键区域和人脸证据，避免用单一置信度阈值取舍。
3. 对 4K 画面评估分块 YOLO 或按区域高分辨率二次检测，平衡小目标召回率和实时 FPS。
4. 针对摄像机视角补齐人员人脸样本，重新构建本地 face DB。
5. 补齐当前机器上的真实 benchmark 输出：YOLO、face detection、ArcFace embedding 延迟及 `nvidia-smi` 显存采样。
6. 增加 Gateway 断流时网页明确显示“等待视频输入”，避免用户误以为 AI 处理卡死。
7. 在不上传隐私照片/模型权重的前提下，补充脱敏测试样本和 CI 测试说明。

## 9. 验证边界

- 已完成 Python 模块编译检查；人员分析单元测试文件已加入仓库。
- 当前环境曾出现 `pytest` 未安装，因此不能把本机最后一次命令报告为 pytest 全部通过；安装开发依赖后再运行测试。
- 原 Gateway 的历史协议、板端、雷达和网络验收文档仍然有效，入口见根目录 `HANDOFF.md`、`docs/DEPLOYMENT.md`、`docs/ACCEPTANCE.md`。
- 4K 输入、GPU provider 正常、相机是否持续推流、人脸是否能被可靠识别是不同层次的结论，交接时必须分开报告。

## 10. Git 上传边界

上传内容包括源码、配置模板、启动/诊断脚本、测试和文档；不上传：

- `.venv`、`.venv_ai`
- `data/persons` 人脸原图
- `data/face_db/*.json` embedding/index
- `models/*.pt`、`*.onnx`、模型压缩包
- `runtime` 日志和现场运行产物

如果部署人员需要模型和人脸库，应通过受控的现场介质或私有存储单独分发，不要提交到公开仓库。
