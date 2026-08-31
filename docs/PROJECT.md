# 项目说明

版本基线：2026-08-31；以本目录新报告为准，归档中的“全部正常”“720p”“板端热插拔已通过”等历史说法不得直接沿用。

## 1. 目标与范围

RK3562 将 MC800S 相机和 XT-M60 雷达数据转换为《空间相机通信协议 V1.0》的 Zenoh / Protobuf 消息。PC 负责协议接收、原生 JPEG 解码显示和点云可视化。用户已授权板端修改，本轮已重新编译部署，具体见BOARD_FIXES；不修IMU业务、不降分辨率、不重新引入H264路径。

板卡型号由设备树 `rockchip,rk3562`、`uname` 确认。此前笼统称 RK3566 的描述不应当作当前板卡识别结果。

## 2. 网络和进程

```text
MC800S 192.168.0.123 -- HTTP JPEG -- RK3562 xt_camera :7448
XT-M60 192.168.0.101 -- TCP控制/UDP -- RK3562 xt_radar :7447
                                          |
                             eth1 192.168.0.250 (交换机)
                                          |
                               PC 192.168.0.200 / 千兆网卡
                                          |
                             pc.gateway (两个独立 Zenoh session)
                                 |                    |
                          HTTP :8080          Foxglove SDK :8766
                           原图/状态             相机 + 点云
```

当前雷达、相机、PC及板端eth1均通过交换机连接；eth0无链路。雷达驱动从持久radar_network读取eth1/192.168.0.250，控制与UDP目标一致。旧拓扑eth0/.179仅作可选兼容，不能继续强制旧主机路由。板子还有历史`.1.179`、`.2.179`地址及经`.1.200`的默认路由，不应据此保证互联网畅通。本机“以太网4”实测协商为**1 Gbps**；不执行强制10Mbps或定时重置网卡。

板端 `/userdata/xtapp/xt_camera`、`xt_radar` 由 init 脚本启动。PC 的 `YunKeAutostart` 在 SYSTEM 下运行 `start_yunke.ps1`，守护一个网关进程树。Python venv 在 Windows 上存在引导进程与实际子进程，这不等于启动了两个网关；8080/8766 应由同一个实际 PID 监听。

## 3. 相机路径

MC800S `/cgi-bin/snapshot.cgi` 的 `stream=1` 原生生成 1920×1080 JPEG。板端 HTTP 获取完整文件，仅包装 Header、ImageMsg 和 ImageMsgArray，通过 `active/LX2601F10001/image` 发布。

- 顶层必须 `ImageMsgArray`，单帧 array 长度 1。
- `format=2`，width/height 与 JPEG 实际尺寸一致，data 为完整 JPEG 文件。
- 不进行 H264 解码、不进行 JPEG 二次编码。图片上的日期是相机 OSD；PC 不修改图内文字。
- 历史 `stream=0` 是 720×480，不是 1280×720。当前不切换它；没有本轮 720p Zenoh 测量。
- HTTP客户端支持Keep-Alive，但相机实际逐次关闭连接，不能宣称相机支持持久连接。当前libcurl版本已经处理Connection:close、chunked、断线重连，连接期限150ms、整次GET总期限350ms。
- 板端采集/发布线程分离，队列 3 帧；PC 每路接收队列 4 帧。满队列舍弃旧帧、计数，不允许无限积压；这不是“每帧抽点”。拥塞时不能保证无损保存每个时刻的帧。

PC 回调只复制入队；解析/适配在工作线程。网页通过内存中的最新 JPEG 获取数据，不再经过逐帧写 `camera_latest.jpg` 的磁盘链路。网页只把新 frame_id 的成功解码计入显示 Hz，停止收到新图会标为 STALE。

## 4. 雷达路径与点数

主主题是 `active/LX2601F10001/pointcloud`，不要订阅旧 preview/UDP 旁路来进行协议验收。每个点的 x/y/z 以 scaler=1000 从整数毫米转换到米，PC 对每个收到的点逐一保留顺序和数据。单元测试覆盖 10000 点，现场消息约 5300–6300 个有效点，**没有 96 点上限**。

9600=160×60 是原始采样槽位数。板端过滤无效距离、非有限坐标，并使用 SDK 示例的四角裁剪；因此“Foxglove 显示协议收到的全部有效点”不等于“板端发送全部 9600 槽位”。当前约 4.7 Hz、约 5800 点/帧，约为 2.7 万有效点/秒；4.8 万是 9600×5 的理想原始槽位量，不能据此强行补点。

Foxglove 显示 `foxglove.PointCloud`：步长 40 字节，小端；x/y/z 为 float64，rgbi 为 uint32，intensity 为低字节，ring 为 uint32，offset 为 int32。当前 RGB、ring、offset 在上游都是 0；彩色显示是基于强度或坐标的伪彩，不是相机颜色融合。

## 5. 坐标和时间

Foxglove 相机 frame_id=`camera`，点云 frame_id=`lidar`。无已验证的相机-雷达外参，不能伪造 TF 把点投到图片上；双面板同时显示不等于空间配准或同步曝光。

板端 camera stamp 来自抓图请求前的 monotonic clock，点云 stamp 来自雷达帧；两者 epoch 不同。Foxglove 展示时间采用 PC 收到该消息时的 Unix ns，原始 stamp 不改写，保存在原始 Protobuf、状态和验收文件中。源端序号或时间回退会统计；重新启动后回退应解释为重置，不直接叫网络丢包。

板端 RTC 当前为 1970 年。相机 OSD、雷达时钟、板端 RTC、PC 时钟是不同来源。网页的 age 是 PC 收到新数据后的时长，**不是测出的曝光到显示总延迟**。

## 6. 原始记录和资源

点云原始 Protobuf 异步写到 `raw_data/pointcloud/pointcloud-*.bin`，每约 60 秒分片，保留最近 5 分钟及分片边界余量。每条 `[8 字节源 stamp ns][4 字节 payload长度][完整 LidarPointMsgArray]`，小端。写线程队列 64；磁盘异常与丢弃计数在 `/api/status` 的 recorder 中。强杀进程可能使当前分片尾部不完整，读取器应忽略不足长度的末记录。

不默认落盘每张相机 JPEG，避免无必要 IO。旧 `raw_data/raw-*.bin` 是历史证据，当前记录器不删除它。网关常规日志按 4 MB×4 轮转；板端 `camera.log` 仍无轮转，是待修风险，不可声称整套系统日志都已限额。

PC 接口默认只监听 loopback。板端和相机仍使用开发阶段凭证/明文局域网连接；公网部署前必须隔离网络、移出硬编码凭证并单独评审安全策略。
