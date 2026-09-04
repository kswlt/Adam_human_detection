# 人员分析使用

启动 Gateway 后运行：

```powershell
.\start_person_analytics.ps1
```

默认从 `http://127.0.0.1:8080/latest.jpg` 读取现有网关 JPEG，并在 `http://127.0.0.1:8090/analytics` 提供分析页面。

等价的明确命令：

```powershell
.\.venv_ai\Scripts\python.exe -m pc.person_analytics.app --source gateway
```

当前 `config/person_analytics.yaml` 的 `runtime.require_gpu: true` 会在 CUDA/ORT/PyTorch 不可用时直接失败并打印完整 traceback；不会静默切换 CPU。页面和 `/api/analytics` 会显示 Camera FPS、AI FPS、Face FPS、检测设备、InsightFace provider、延迟、队列长度和丢帧数。

无硬件时：

```powershell
.\.venv_ai\Scripts\python.exe -m pc.person_analytics.app --source video --video tests/data/workshop.mp4
.\.venv_ai\Scripts\python.exe -m pc.person_analytics.app --source image-dir --image-dir tests/data/images
```

输入帧采用有界最新帧策略；检测器只保留 person 类。当前没有标定文件时坐标为 image pixels，不声称为米制世界坐标。

接口：`/analytics` 页面、`/api/analytics` 实时状态、`/api/analytics/today` 今日累计、`/analytics/person/<person_id>` 详情与轨迹、`/frame.jpg` 当前叠加帧。
