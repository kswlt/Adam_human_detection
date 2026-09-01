# 云科空间相机协议网关

2026-08-31 本机交付版。硬件：Rockchip RK3562、芯探 XT-M60、MC800S。

**当前相机支持原生1080p JPEG/H264协议输出，最终运行JPEG；浏览器可看JPEG画面。雷达仍有独立现场异常，整体协议不能判为全部合格。**
板端已更新原生JPEG HTTP采集、共享持久配置、config_file、雷达断流恢复与解析边界。当前改动及新证据见[板端修复记录](docs/BOARD_FIXES.md)。30分钟验收仍暂缓；短测不代替物理拔插或全协议验收。
甲方确认的setting为0不修改、1 H264、2 JPEG；发布format分别为3和2。H264使用MC800S原生RTSP码流和`-c:v copy`，没有重新编码。完整结果见[相机双格式交付记录](docs/CAMERA_DUAL_FORMAT_20260901.md)。PC生产网关按任务边界仍只显示JPEG，因此最终配置保留JPEG。
当前为共享交换机拓扑，雷达也经板端eth1访问；radar_network持久配置为eth1/192.168.0.250。旧eth0直连说明只适用于旧接线。

## 打开画面

- 浏览器：[相机实时画面](http://127.0.0.1:8080/)。网页不缩小 JPEG 文件、不重新编码；适应窗口显示不会改变源分辨率。
- Foxglove：Foxglove WebSocket 连接 `ws://127.0.0.1:8766`，3D 面板选 `active/LX2601F10001/pointcloud`，图像面板选 `active/LX2601F10001/image`。3D 显示参考系为 `lidar`。
- 状态：[实时状态 JSON](http://127.0.0.1:8080/api/status)。关注新帧 age、实际 Hz、invalid、queue_dropped、reconnects，不以进程存在或 put=0 代替收包证明。
- 本机 `YunKeAutostart` 计划任务运行网关守护；不要再启动旧的 EXE 桥或 MJPEG 服务。

## 文档入口

| 文档 | 内容 |
| --- | --- |
| [项目说明](docs/PROJECT.md) | 架构、网络、数据路径、坐标、时间和边界 |
| [构建部署与运维](docs/DEPLOYMENT.md) | 安装、运行、Foxglove、故障定位、回滚 |
| [协议逐项审查](docs/PROTOCOL_AUDIT.md) | 格式/频率/指令/配置/QoS/热插拔的独立结论 |
| [验收报告](docs/ACCEPTANCE.md) | 100/1000 帧、最终短测、恢复测试、待验项 |
| [变更与清理](docs/CHANGES.md) | 修改了什么、未修改什么、历史文件去向 |
| [板端修复](docs/BOARD_FIXES.md) | HTTP停顿、文件通道、持久化、断流恢复及本轮证据 |
| [相机双格式](docs/CAMERA_DUAL_FORMAT_20260901.md) | MC800S H264接口、协议封装、切换、重启和解码证据 |
| [需求边界](docs/REQUIREMENTS.md) | 用户补充约束与协议歧义 |
| [交接入口](HANDOFF.md) | 下一位开发者必读的当前状态 |
| [审查摘要](CODEX_AUDIT.md) | 主要阻断项和证据索引 |

## 目录

```text
board/src/         当前板端 C++ 源码及共享配置、HTTP、请求解析头文件
board/init/        板端原有启动脚本，内容未改
board/bin/         与板端哈希一致的二进制快照
board/build.sh     交叉/原生构建入口，已在板端xtbuilder完成原生构建
pc/                唯一 PC 运行实现：Zenoh + Foxglove SDK + HTTP + 异步记录
protocol/          V1.0 Protobuf 定义
config/            PC 连接和服务配置
tests/             单元、独立订阅、模拟断流、守护和只读指令测试
docs/reference/    协议原件、硬件资料和报价原件
evidence/          验收 JSON、CSV、原始消息/JPEG 样本
vendor/            Zenoh、libcurl、nlohmann/json、雷达 SDK 参考及许可证
runtime/           运行日志
raw_data/          点云原始记录，历史文件保留
archive/           旧脚本/日志/二进制/文档的回滚归档，不参与运行
scripts/           一次性整理脚本，不要再次执行
```

开发环境：Windows / Python 3.13.2。执行 `./setup_pc.ps1` 后用 `.venv/Scripts/python.exe -m unittest tests.test_gateway -v` 验证。
图像/点云仍是标准 Zenoh + 原协议 Protobuf；Foxglove 格式仅是 PC 显示适配层，不是替换板端协议。
