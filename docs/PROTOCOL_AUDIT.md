# 协议与恢复能力审查

日期：2026-08-31。结论：**数据格式主要路径通过，整套系统不满足严格全项验收。**
2026-09-01覆盖：甲方已正式确认setting image_format为0不修改/1 H264/2 JPEG，原PDF冲突不再是待确认项。JPEG/H264双格式已部署，详见[相机双格式交付记录](CAMERA_DUAL_FORMAT_20260901.md)；下表中的JPEG-only、setting未实现等行是修复前历史，不代表当前源码。
本页原矩阵为修复前审查。随后按用户要求完成板端修复，最新实现/测试见[BOARD_FIXES](BOARD_FIXES.md)：config_file、原子持久化、坏请求拒绝、实际配置回读、HTTP总期限/连接处理、FrameInfo/UDP边界、独立seq、工厂SN只读、持续断流恢复均已补齐。断链发现的专用路由丢失也纳入恢复。保留下面原始发现供追溯，不能再将其中“未实现”当作当前源码状态。
依据原件 `reference/2-空间相机通信协议V1.0.pdf`，SHA256 `5BDA83FFE90A4321091E15AD09340D06FA5B1CB14CD56A61F013611F020759B0`。
独立检查使用 `protocol/active_msgs.proto` 生成的官方 Protobuf 解析器，不再使用板端同一手写解析器来互相证明正确。

## 1. 逐项结论

| 项目 | 结论 | 实现/证据与边界 |
| --- | --- | --- |
| SN 文件读取与主题命名 | 部分通过 | 两主题实际 SN= LX2601F10001；读取 Lixel.yaml。但启动调用 save_sn 覆盖整份工厂 YAML，且仍是示例 SN，唯一性待确认。源码 xt_radar.cpp:111、736 |
| image 顶层 Array | 通过 | 1000 帧全部 ImageMsgArray，长度 1；官方解析成功 |
| JPEG=2、完整字节、真实宽高 | 通过 | 1000 帧 1920×1080；SOI/EOI、Pillow 完整解码通过；最终短测 Foxglove 与独立接收 JPEG 哈希一致 |
| JPEG 原生采集 | 通过本轮路径审查 | xt_camera.cpp 的 HttpSnapshotClient 直接 GET；无 H264→JPEG/二次编码；已知相机能力实测证据沿用，未重复压测相机 |
| image 10 Hz | 未达严格目标 | 1000 帧平均 9.8239 Hz；最终 35 秒 9.4589 Hz，出现 982.5 ms 间隔。没有协议公差，不写“稳定10Hz通过” |
| pointcloud Array/嵌套 points | 通过 | 1000 帧解析、长度1、scaler1000、seq/stamp 通过；最终转换后的全部点字节校验匹配 |
| pointcloud 5 Hz | 未达严格目标 | 1000 帧平均 4.7257 Hz，P99=301.3 ms。源码发布阈值与输入节拍会跳过部分帧，详见 xt_radar.cpp:933 |
| ring/offset/RGB 语义 | 部分/待设备确认 | 当前 ring=0、offset=0、rgbi 仅低8位强度。不能把字段存在说成真实线号/点时差/彩色融合已经实现 |
| IMU 50 Hz | 本轮不验收 | 按用户要求不修改；不计为已通过 |
| config_file | 未实现 | 无 active/{sn}/config_file 发布者、FileMsgArray 或实际文件读取/传输路径 |
| cmd/setting 请求/应答线格式 | 部分通过 | header-only 查询收到合法 SettingResponse；源码 xt_radar.cpp:681 起 |
| setting 错误码 | 不通过 | 实际发送损坏 PB `80`，仍 code=0/success；协议要求解析失败 code=1。证据 commands-20260831.json |
| setting 持久化/重启生效 | 不通过 | 只写 g_* 内存变量，无落盘/加载；图像当前返回 fps=0、format=0，与运行状态不符 |
| reboot 回复后500ms重启 | 未实测 | 代码有逻辑，阻塞 read callback 500ms；本轮没有触发板子重启，不证明回复真正发完 |
| config.json/zenoh 配置 | 不通过 | 板端 peer、7447/7448 硬编码；没有按第9节加载 mode/connect/listen/scouting |
| 默认多播发现、router、多设备 | 未验证/未配置化 | 当前通过明确 TCP endpoint 连接，PC 禁用 scouting。库编译启用发现不等于实际拓扑已经验收 |
| QoS 推荐值 | 未显式符合 | 发布者使用默认选项；本地库默认 Reliable+Drop，协议推荐数据 BestEffort+Drop。QoS 表用“推荐”，与强制 Array 区别说明 |
| PC 队列/陈旧状态/自动重连 | 通过短测 | 独立模拟真正关闭 Zenoh 服务，状态失活，服务恢复约0.317s重收；不是物理拔插测试 |
| PC 进程守护 | 通过实测 | 杀死实际网关进程，计划任务自动恢复两路，约3.298s |
| 板端相机拔插 | 部分/待物理验证 | 抓图失败重连已有代码；没有总体请求期限，未实拔；init不幂等且没有进程退出守护 |
| 板端雷达拔插/断流恢复 | 源码不通过且现场暴露恢复失败 | xt_radar.cpp:982 的 frames==0 限制导致已出帧后断线不进入该重连逻辑；最终巡检已发现设备可ping但源停止出帧，需手动重启服务恢复。没有实际物理拔插测试 |
| 开机自启 | 配置存在/部分实测 | 本机计划任务手动启动已运行；板端init存在。未进行本轮真实PC/板卡断电重启验收 |

表内 C++ 路径位于 `board/src/`。所有通过仅限定于对应测试范围，不意味着每条异常路径、所有网络拓扑或长时间运行都合格。

## 2. config_file 到底是什么

它是协议第6节规定的**文件数据通道**，例如发送标定文件：

```text
topic: active/{sn}/config_file
payload: FileMsgArray { array: [
  FileMsg { header: ..., path: "device_calib_info", data: <真实文件字节> }
] }
```

它不是“JPEG格式有问题”，不是网页文件，也不是第9节配置 Zenoh 连接用的 `config.json`。当前相机和点云能显示，并不能补齐这个文件通道。正确实施需要确认真实标定文件来源、path 的约定、何时触发发送和接收方需求；不能发送空文件或伪造外参冒充完成。协议对按需触发方式/目录范围描述不足，应在实施前补充接口约定。

## 3. 主要工程风险

1. **雷达内存安全**：xt_radar.cpp:518 接受 infosize 100–300，:521 按该长度 memcpy 到固定 FrameInfo，未限制到 sizeof；较短帧也可能留下未初始化字段。UDP 重组 :436–464 按收到字节累计，不去重片号，且需完善总长上限/重复包/越界检查。应在下次板端部署前修复并做异常包测试。
2. **雷达恢复失效**：已经收到第一帧后再断流不会触发 frames==0 的恢复分支。PC 订阅恢复无法替代雷达硬件重连。
3. **相机仍可能上游停顿**：xt_camera.cpp:243、278、301 使用逐次 IO 700ms 等待，不是整个 GET 的绝对期限；HTTP Connection:close 未正确处理、send 未抑制 SIGPIPE、阻塞 socket 的写也没有总期限。最终短测直接收包与显示均出现约1秒间隔，随后下一帧源时间也跳变约982.6ms，与相机获取阶段延迟相符，但未做分阶段埋点，不能唯一归因。
4. **工厂数据保护**：save_sn 使用写入截断方式，覆盖 Lixel.yaml 其他键。应只读既有SN；需要初始化时以结构化 YAML 保留其他字段，禁止每次启动覆写。
5. **命令与数据序号共用**：g_seq 同时用于点云和 setting/reboot 回复。查询命令会制造点云seq空洞；不能一律统计成链路丢帧，应分开序列。
6. **时间及服务**：雷达调度/reconnect 使用 system_clock，校时时钟跳变可能影响周期；板端无常驻进程守护、相机日志不轮转、相机重复start可能抢7448。
7. **网络/安全**：S98xtnet 改全局 FORWARD 策略并清空 DOCKER-USER，可能影响同板其他服务安全策略；本轮未执行或修改该脚本。配置凭证、IP/SN和端口硬编码，不能直接作为生产安全交付。

## 4. 协议歧义与待签字项

- `SettingRequest.image_format`冲突已由甲方确认覆盖：0不修改、1 H264、2 JPEG；`ImageMsg.format`仍是H264=3、JPEG=2。PDF仍未规定H264 data的AU/NAL及Annex-B/AVCC边界，当前采用一个完整Annex-B access unit并保留为互通确认项。
- 1080p 出现在带宽估算，用户额外要求1080p优先，当前按此保持；不要把估算中的数据量当每帧最小字节数。
- 时间戳单位/epoch、0值 ring/offset 的设备适配规则、seq 重启规则和频率公差应明确。没有公差时本报告不判定9.82等于10。
- QoS 表给出的 RealTime(6) 与所用 Zenoh 枚举语义需核对，配置应依据实际 API 枚举而非照抄不一致数字。

## 5. 建议修复顺序

先修板端解析边界和运行后断流恢复；再补相机 HTTP 总请求期限/Connection:close/SIGPIPE 处理以及分阶段耗时计数。之后实现共享持久配置、setting错误码与实际值回读、真实config_file；最后执行物理热插拔、断电重启、router/QoS测试与被暂停的30分钟测试。
全过程保留原生1080p JPEG，并以相机原生H264直通扩展；不自行降分辨率、转码或通过重复旧帧凑10Hz。

## 6. 交付前追加现场事实

10:29左右的独立8秒测试，图像80帧、点云0帧。板端雷达PID仍存在、carrier=1、ping通，日志却停止在seq20184，PC已重连120余次。因此这不是Foxglove单纯没显示，也不能以进程存活认定健康。随后仅执行S99xtradar restart，PID4755→4850，数据恢复；没改源码或重启系统。最初停止出帧的原因仍需查硬件/驱动。

此时累计PC图像计数还出现queue_dropped=1、seq_gaps=113，属于短测窗口之外的事实，来源需另查，不可宣称本轮全过程零丢帧。各独立100/1000帧窗口的0错误结果保留，但不能外推。证据见final-discovered-outage、final-outage-direct、post-radar-recovery和final-runtime-after-recovery文件。
