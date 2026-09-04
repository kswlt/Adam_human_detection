# GlobalPerson 进展（2026-09-04）

## 已接入

- 人体检测仍由 YOLO person class 0 完成，和人脸入口分离；GPU 设备由 `runtime.device` 控制并由 `require_gpu` fail-fast。
- 生产短期跟踪器仍是官方 Ultralytics ByteTrack；`track_id` 只表示短时运动轨迹。
- `GlobalPersonManager` 为当天目标生成 `DAY_YYYYMMDD_NNNN`，API 同时返回 `global_person_id`、`known_person_id`、`track_id`、`track_state` 和 bbox。
- 同一已确认人脸在 tracker 换 ID 后会重新挂回原 GlobalPerson；未知目标也会被统计为合法 GlobalPerson。
- `WorkTimeAnalyzer` 的共享实例按 GlobalPerson 复用，避免同一稳定身份因多个 track 产生重复工时；关闭时对共享实例去重。
- `DailyAppearanceGallery` 实现了有限 gallery 及 `MATCHED / AMBIGUOUS / NEW` 拒绝匹配规则。
- `AppearanceEncoder` 提供 ONNX body ReID 接口，但当前机器/仓库没有 `models/osnet_x0_25.onnx`，因此实时状态明确报告 `unavailable`，没有假装使用 ReID。
- analytics API 已输出 `raw_detection_count`、`tracker_output_count`、`confirmed_track_count`、`global_person_count`、`api_people_count` 和 ReID diagnostics，便于区分检测、跟踪、业务过滤和 UI 问题。

## 真实验证

当前 `8090` Gateway 模式实测：camera 11.59 FPS，AI 11.97 FPS，detector 31.59 FPS，face 6.30 FPS，端到端 latency 79.26 ms；YOLO `cuda:0`、ByteTrack `ultralytics.bytetrack`，raw detections 4、confirmed tracks 4、API people 4。输入 Gateway healthy，当前 frame queue 丢旧帧而不积压。

## 当前明确未完成

1. OSNet/其他成熟 body ReID 模型文件尚未提供，因此跨 track 的未知人员只能保留为新的 GlobalPerson，不能声称已完成衣着 ReID 重关联。
2. GlobalPerson 当天状态尚未从 SQLite 完整恢复到内存管理器；已有轨迹/脸库数据库仍可用，但服务重启后的稳定身份续接还需要补迁移和恢复逻辑。
3. face 仍使用当前 InsightFace 结果作为绑定证据；多人交叉时的全局 ReID one-to-one assignment、tracklet lost gallery 和人工标注 recall 评估仍需现场视频验收。

以上限制会在 API diagnostics 中显式呈现，不会静默 CPU fallback 或把 Unknown 强行匹配给某个员工。
