# MC800S JPEG/H264 双格式交付记录

日期：2026-09-01。当前运行配置最终恢复为 JPEG：`image_format=2`、10 Hz、1920x1080；H264 配置保留为 GOP 20、4 Mbps，可通过 setting 切换。

## 实际接口与封装

1. MC800S H264 来自 ONVIF `MainStream` 返回的 RTSP 地址结构 `rtsp://192.168.0.123:554/stream0?...`，不是猜测 URL。生产代码保留相机返回的 MD5 查询参数；本文不重复展示凭证。
2. 最终 ONVIF 配置为 H264 High、1920x1080、10 fps、4096 kbps、GOP 20。原始响应见 `evidence/mc800s-onvif-profiles-final.xml`，能力响应见 `mc800s-onvif-options-final.xml`。
3. 板端使用现有 `/userdata/xtapp/ffmpeg` 拉 RTSP/TCP，参数包含 `-c:v copy`，只做 RTSP/RTP 解包和码流复制，不解码、不重新编码。
4. H264 发布为 Annex-B。一个 `ImageMsg` 对应一个完整 access unit；顶层始终是长度1的 `ImageMsgArray`，`ImageMsg.format=3`。
5. 解析器缓存 SPS/PPS；每个 IDR 缺参数集时会补入缓存。实测 GOP 20，每个 IDR access unit 都含 SPS/PPS。SPS 解析出的发布尺寸为1920x1080。
6. JPEG 路径不变：原生 snapshot完整文件、不缩放、不重编码，`ImageMsg.format=2`。
7. timestamp 是 access unit/JPEG 在板端取得时的 monotonic 时间；协议未规定 H264 PTS/epoch，因此没有伪造相机 PTS。

## Setting 行为

| SettingRequest.image_format | 行为 | 实际 ImageMsg.format |
| ---: | --- | ---: |
| 0 | 不修改 | 保持当前值 |
| 1 | 持久化H264并仅重启相机服务 | 3 |
| 2 | 持久化JPEG并仅重启相机服务 | 2 |

其他值及负数返回参数错误。H264按真实1080p能力限制为5..10 Hz、GOP 1..200、码率1..9 Mbps；配置值0仅表示不修改已有GOP/码率。相机重启改为隔离的`fork/exec`，子进程先关闭继承fd，避免相机占住雷达7447监听端口。

## 真实设备结果

| 测试 | 帧数 | 平均Hz | P50 ms | P95 ms | P99 ms | 最大ms | 失败/丢帧 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| JPEG正式1000帧 | 1000 | 9.939858 | 100.076 | 106.521 | 111.626 | 203.617 | 0 |
| H264正式1000帧 | 1000 | 10.000255 | 100.034 | 106.316 | 115.020 | 118.959 | 0 |
| H264三分钟 | 1800 | 10.010749 | 100.062 | 105.984 | 111.965 | 113.662 | 0 |
| 最终JPEG | 100 | 9.999793 | 100.550 | 107.455 | 110.295 | 111.033 | 0 |

- JPEG 1000张全部通过官方Protobuf解析、array长度、format、尺寸和Pillow完整解码。
- H264三分钟1800帧全部通过Protobuf、Annex-B、VCL、尺寸、seq和timestamp检查；90个IDR均带SPS/PPS。
- 独立订阅从遇到的首个IDR开始写解码文件，因此跳过最初19个P帧；写入的1781个access unit被另一套Windows FFmpeg标准H264解码器全部解出1781帧。日志为`evidence/camera-h264-production-3min-1800-ffmpeg-decode.txt`。
- 板上旁路测得`xt_camera`约2.1% CPU、copy-only ffmpeg约2.3% CPU；不同采样时刻会波动。
- JPEG→H264→JPEG→H264及额外隔离切换均实测payload，不只检查配置。各轮JSON见`evidence/camera-switch-*.json`和`camera-isolated-restart-*.json`。
- H264和JPEG分别执行整板reboot。两次都保持配置并由init自动启动对应输出；证据为`camera-persistence-*-after-reboot.json`。
- 隔离修复后切换期间`xt_radar` PID保持1290；7447仅由xt_radar持有、7448仅由xt_camera持有。源雷达当时已处于无有效帧状态，因此只能证明进程/端口不受相机切换影响，不能把点云数据连续性写成通过。

## 修改文件

- `board/src/xt_camera.cpp`：双采集模式、ONVIF H264配置、copy-only ffmpeg子进程、自动重连和统一协议发布。
- `board/src/h264_annexb.hpp`：Annex-B NAL/access-unit解析、SPS尺寸、SPS/PPS缓存。
- `board/src/device_config.hpp`：正式setting枚举、默认H264参数及真实能力边界。
- `board/src/xt_radar.cpp`：setting持久化后的相机专用重启及fd隔离；未改雷达采集算法。
- `protocol/active_msgs.proto`：记录已确认setting映射和H264 access-unit约定。
- `tests/h264_unit.cpp`、`tests/audit_camera_formats.py`及相关测试入口：独立协议与解码验证。
- `board/bin/xt_camera`、`board/bin/xt_radar`：同步最终部署二进制。

最终二进制SHA256：xt_camera `6601B46C4A4D708FC31B3FEF25BC0A51FB8A2C1DA63ADC4B125FF1170D13808B`；xt_radar `780E971053C100212C2F1B24112E6E20BF3FA56AAC81FBFE903DD48CED5FF4E2`。

## 保留风险

- 协议PDF没有定义H264 data的NAL/AU和Annex-B/AVCC边界；本实现采用最通用的完整Annex-B access unit。甲方接收端仍应确认这一互通约定。
- 按任务边界没有修改JPEG-only PC网关。因此切到H264时8080/Foxglove图像不会解码H264；本轮PC显示证据来自独立订阅导出后标准解码器，不是生产网页。最终留在JPEG以保持现有本机画面。
- setting成功应答表示配置已原子持久化且已安排相机重启；重启后ONVIF/RTSP若发生新的设备故障，只能在camera.log看到失败，原应答无法追溯改写。
- H264新订阅者可能等待到下一个IDR，当前最坏约2秒；不会永久缺SPS/PPS。
- H264依赖板上现有ffmpeg可执行文件。文件被删除或能力裁剪后H264会重连失败，但JPEG不受影响。
- 本轮H264连续测试为3分钟，不是30分钟；用户已明确暂不做30分钟验收。
- 雷达源当前异常不在本任务范围，不能据相机隔离测试宣称整套点云链路恢复。
