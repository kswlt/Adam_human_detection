# 人员分析系统架构设计

状态：Phase 0～12 的离线 MVP 已实现；2026-09-03 已完成 GPU、视频模式和真实 Gateway HTTP 帧源端到端验收。生产 Gateway 本身仍保持独立运行。

## 当前仓库与数据链路

当前项目是一个稳定运行的 PC 网关，不是空白应用。MC800S 由板端 `xt_camera` 通过 HTTP snapshot 获取原生 1920x1080 JPEG，板端包装成 `ImageMsgArray`，发布到 `active/LX2601F10001/image`。PC 的 `pc.gateway.Source` 为该主题建立 Zenoh subscriber；Zenoh 回调只复制 payload 和时间戳并放入 `queue.Queue(maxsize=4)`，满队列时丢弃旧帧。独立工作线程解析 protobuf、校验完整 JPEG、调用 Foxglove `CompressedImage` channel，并在 `Source.latest` 中保留最近一帧的原始 JPEG 和元数据。

现有 HTTP 服务复用这份内存快照：`/latest.jpg` 返回原始 JPEG，`/api/image.pb` 返回原始 `ImageMsgArray`，根路径页面轮询前者。点云有独立 Source 和异步原始记录器；Foxglove 由同一个网关进程在 8766 提供图像及点云通道。现有链路已有有界队列、沉默检测、Zenoh 自动恢复和状态诊断。

## 关键边界

人员分析只消费 PC 已成功解析的 JPEG，不修改板端源码、protobuf、原始图像字节、Zenoh topic、点云适配或 Foxglove channel。AI 失败、模型缺失、数据库异常和 Web 客户端断开都必须被分析模块自身捕获，不能让网关采集线程退出。

## AI 接入位置

Phase 1 在 `Source.process()` 完成 JPEG 校验并更新 `latest` 后，通过一个可选的 frame sink 发布不可变 `FramePacket`。sink 使用独立的 `Queue(maxsize=2~3)`，采用“丢旧保新”策略；生产者不等待检测、人脸识别或数据库。为避免向已有稳定代码注入运行时耦合，默认不启用 sink，现有网关行为保持不变。后续 `person_analytics` 进程可通过同进程回调或独立 HTTP/共享内存适配器接入。

## 推荐技术栈与环境

当前实际检查结果：系统默认 Python 为 3.9.1；AI 环境使用独立 Python 3.11.9。`.venv_ai` 已验证 CUDA 版 PyTorch、`onnxruntime-gpu` 1.29.0、Ultralytics、InsightFace、OpenCV 与 Gateway 依赖可共存；生产网关环境仍由 `requirements.txt` 独立管理。

因此不修改生产 `.venv` 的 Python/依赖。AI MVP 使用单独 `.venv_ai`；当前 NVIDIA 机器配置为 GPU fail-fast：CUDA provider 不可用时启动直接输出完整错误，不会把 CPU 结果伪装为 GPU 运行。模型文件放在 `models/`，不提交大文件。

## 目录与数据流

```text
pc.gateway Source.process
  -> FrameSink / bounded latest-frame queue
  -> person_analytics capture adapter
  -> AI worker: person detector -> tracker -> scheduled face recognition
  -> temporal identity fusion -> trajectory/prediction -> zones/work time
  -> batched SQLite writer
  -> analytics API/WebSocket -> /analytics
```

建议新增 `pc/person_analytics/`，内部按 capture、detection、tracking、face、trajectory、analytics、storage、web、tools 分层。核心对象使用 dataclass：`FramePacket`、`Detection`、`TrackState`、`IdentityState`、`TrackedPerson`。

## 线程/进程模型

现有 Zenoh 接收和解析线程不阻塞。Phase 1 sink 仅 `put_nowait`。MVP 默认分析 worker 在独立线程/进程运行；模型不兼容或推理崩溃只将 analytics 标记 degraded。数据库采用批量写入线程，Web 使用独立 aiohttp 路由或独立端口；初期不修改既有 `/`、`/latest.jpg`、`/api/status` 语义。

## 模型与跟踪选择

人员检测优先 Ultralytics YOLO 的 person 类，部署时固定模型版本和 SHA256；ByteTrack 负责 track_id 与 LOST grace period。人脸识别使用 InsightFace/ArcFace ONNX，按 track 0.5 秒（Unknown）或 3 秒（Known）调度。身份通过带时间衰减的 vote 累积确认，不把单帧结果直接写入 track。`track_id` 是短期视觉 session，`person_id` 是长期身份；跨 track 再识别需要高置信人脸结果或长期 gallery 匹配。

## 坐标、轨迹与工时

无标定时只输出 image 坐标；`HomographyProjector` 预留 image_points/world_points 转换，配置缺失时明确 `coordinate_mode=image`。轨迹使用 bbox bottom-center，保留最近 30 秒；预测使用平滑后的 constant-velocity/Kalman 模型，提供 0.5/1/1.5/2/3 秒点，静止目标施加最小运动阈值。区域使用 foot point 与 polygon 判断。

工作时长按 timestamp 差值累计，绝不按固定 FPS 加一帧。至少记录 visible/session/zone；短暂掉帧使用 grace period，超过 max_gap 结束 session。Unknown 可跟踪、预测和记录，但不计入实名员工统计；后续确认身份时允许把当前 session 归并。

## SQLite 设计

至少包含 `persons`、`face_embeddings`、`tracks`、`person_sessions`、`trajectory_points`、`zone_events`、`daily_statistics`，对 `(person_id,timestamp)`、`(track_id,timestamp)` 和日期字段建立索引。embedding 以本地 blob/JSON 保存，保留 raw 与 centroid；照片指纹和模型版本用于增量重建。写线程批量提交，失败重试并记录 degraded 状态。

## Web UI

首期提供独立 `/analytics` 页面和 JSON 状态接口，视频使用既有 JPEG URL，叠加框、轨迹、预测和 ROI 可由分析状态绘制到 canvas；不重编码或替换原始预览。人员详情页显示 person_id、头像引用、今日统计、session 和轨迹。UI 显示 CAM/AI/FACE FPS、延迟、队列长度及 dropped frames，并明确模型不可用或数据 stale。

## 性能与风险

现有相机约 10 FPS，AI 队列目标 1~3 帧、允许丢旧帧。CPU 性能必须以实际模型 benchmark 为准，不能预先宣称；先保证 camera/HTTP/Foxglove 不受阻，再按 detector、face、DB 分别测 FPS/延迟。主要风险是 Windows Python 3.13 的 InsightFace 依赖兼容性、模型首次下载、GPU provider 不可用、单目坐标不是米制、遮挡与跨 track 误识别，以及隐私数据本地保护。默认不上传照片/embedding，不调用云端识别 API。

## 当前验收结论

`python -m pc.person_analytics.app --source gateway` 已通过真实生产 Gateway `/latest.jpg` 验证，使用独立 Gateway producer + 有界丢旧队列，不阻塞原网关。`--video` 和 `--image-dir` 也已验证。全仓 unittest 104 项通过；AI 实测 YOLO/InsightFace/ArcFace 均走 CUDA。尚需在目标现场按实际 ROI 标定并完成长时间运行与更多遮挡/多人样本验收。

## 预计改动

Phase 1 已新增 `pc/person_analytics/capture` 的帧模型/队列与网关的可选 frame sink，以及单元测试；不改板端、协议定义和已有 HTTP/Foxglove 数据格式。`config/person_analytics.yaml` 默认 `enabled: false`，避免旧启动任务意外加载 AI。后续阶段再逐步加入模型、数据库和 UI，每阶段运行已有测试与新增测试并记录真实限制。
