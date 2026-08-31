# 构建、部署与运维

## 1. 本机现状与启动

工作目录 `C:\Users\Admin\Desktop\yunke`。已有 `.venv`、依赖和 `YunKeAutostart` 计划任务，通常不需要重复安装。

```powershell
Set-Location C:\Users\Admin\Desktop\yunke
Get-ScheduledTask -TaskName YunKeAutostart
Start-ScheduledTask -TaskName YunKeAutostart
Invoke-RestMethod http://127.0.0.1:8080/api/status
```

计划任务在 SYSTEM 下启动根目录 `start_yunke.ps1`。互斥锁阻止重复守护实例；当前健康检查与源收包恢复是两个层次，前者处理网关死掉，后者处理连接断流。不再周期性重启板端雷达、不按端口乱杀其他程序、不调整网卡。

本轮修正计划任务：不限运行时长、允许电池运行且不因切换电池停止、可用时补启动、失败每1分钟重试最多3次。修改前XML在archive，当前XML在evidence。没有实际拔电测试Windows电池事件，也没有真实重启PC测试开机触发。

需要维护停止时先 `Stop-ScheduledTask -TaskName YunKeAutostart`，再确认8080/8766已释放。若有手动启动实例，先查PID和CommandLine确认为本项目，然后停止相应进程树；不要执行“杀全部python”。Windows venv 可能有引导子进程，用进程树方式退出；本项目守护已对此处理。

## 2. 新环境安装

准备 Windows、Python3.13（含py launcher）、局域网可访问板子；Foxglove Desktop 本轮实测版本3.0.0。

```powershell
Set-Location <项目目录>
.\setup_pc.ps1
.\.venv\Scripts\python.exe -m unittest tests.test_gateway -v
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_yunke.ps1
```

`setup_pc.ps1` 创建独立venv，安装锁定版本，依据 `protocol/active_msgs.proto` 生成 `pc/active_msgs_pb2.py`。运行包版本见requirements.txt，生成器见requirements-dev.txt。无需PC端FFmpeg、手写WebSocket实现或旧zenoh-pico EXE。

新电脑上的任务创建示例（管理员PowerShell，显式指向新目录）：

```powershell
$root = (Get-Location).Path
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$root\start_yunke.ps1`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName YunKeAutostart -Action $action -Trigger $trigger -Settings $settings -User SYSTEM -RunLevel Highest
```

不要在已有机器盲目加`-Force`覆盖任务。计划任务需要目录读写权限；运行账号必须可访问venv和runtime/raw_data。

## 3. 配置与接口

`config/pc.json` 仅是PC网关配置，不能补齐板端协议要求的config.json。

| 字段 | 当前值/作用 |
| --- | --- |
| sn | LX2601F10001，匹配板端主题 |
| image_endpoint | tcp/192.168.0.250:7448 |
| pointcloud_endpoint | tcp/192.168.0.250:7447 |
| bind / http_port / foxglove_port | 127.0.0.1 / 8080 / 8766 |
| stale_seconds / reconnect_seconds | 3 / 8 |
| record_pointcloud | true，异步记录原始点云 |

修改配置后重启本机网关生效。独立临时网关必须使用不同端口，并避免同时记录到同一raw目录。板卡相机默认1920×1080；不要在不确认时改snapshot stream。

reconnect_seconds现为沉默告警阈值，不是周期重建会话计时器。保留订阅由Zenoh自动重连；只有实际关闭/异常才重建。/api/status新增stale_events、process_max_ms、sdk_log_max_ms、queue_delay_max_ms和diagnostics.event_loop_lag_max_ms。

### 当前交换机拓扑

用户已将路由器换成交换机，雷达也接到同一交换机。板端eth0无链路，eth1=192.168.0.250；PC=.200、相机=.123、雷达=.101。本地通信不依赖默认网关，不能沿用旧的eth0直连路由。

新版xt_radar读取共享配置中的可选radar_network，指定interface和source_address；旧配置缺省仍兼容eth0/.179。当前交换机配置为eth1/.250，雷达cmd19的目标同时改为192.168.0.250:7687。维护命令先原子保存，随后只重启雷达服务：

```sh
/userdata/xtapp/xt_radar --network eth1 192.168.0.250
/etc/init.d/S99xtradar stop
/etc/init.d/S99xtradar start
```

驱动启动/重连恢复指定网口的雷达/32路由，不改默认路由。只有真正接回eth0直连时才切换为--network eth0 192.168.0.179。不要重跑会清防火墙的S98xtnet；不要在共享交换机拓扑用ip link set eth1 down做雷达单路故障实验。旧tests/board_faults.sh已加eth0路由前置检查，不符合时拒绝测试。

- `/`：实时JPEG页面。
- `/api/status`：每路收到数、转发数、最新age、5秒窗口Hz、seq空洞、invalid、queue_dropped、reconnects、原始stamp、记录器状态。
- `/latest.jpg?after=<frame_id>`：最多1秒等待新帧；无新帧204，首次候选已过期503。JPEG内容不缩放、不重编。
- `/api/image.pb`：最近一条**原始 ImageMsgArray**，用于第三方核对；仅提供最新消息，不是历史录像。
- 响应头 X-Frame-Id、X-Source-Seq、X-Frame-Age-Ms、X-Jpeg-Sha256 可辅助核对。

## 4. Foxglove

添加Foxglove WebSocket连接 `ws://127.0.0.1:8766`；同一连接添加3D和图像两个面板。
3D选 `active/LX2601F10001/pointcloud`，显示参考系`lidar`，启用主题可见性；近距离桌面场景需要缩放到约1–3m，并平移目标到中心。变换设置中关闭大型标签，避免标签挡住点。图像面板主题选`active/LX2601F10001/image`，不要开启没有标定依据的投影。

本轮已实际看见两路同时显示；导出布局的界面操作被用户中止，**没有交付经过验证的布局JSON**。上述设置可手动复现，不要假定config目录中存在可导入的布局文件。

使用官方客户端支持的 `foxglove.sdk.v1` 子协议；自制WS测试若仅声明旧`foxglove.websocket.v1`可能400。板端并非直接发送Foxglove schema，PC作格式适配。参考：[Foxglove SDK WebSocket](https://docs.foxglove.dev/docs/sdk/websocket-server)、[CompressedImage](https://docs.foxglove.dev/docs/sdk/schemas/compressed-image)。

## 5. 板端定位与构建

SSH主机 `root@192.168.0.250`，固定指纹：
`SHA256:Oa6mKwXI0b7Ybt3BYNnI7LAeU1eWYHl6bgCQ85bvsuM`。
凭证沿用现有设备配置，不在交付文档再次散布明文密码；连接时输入已配置密码或使用本地安全凭证。

```powershell
plink -ssh -hostkey SHA256:Oa6mKwXI0b7Ybt3BYNnI7LAeU1eWYHl6bgCQ85bvsuM root@192.168.0.250
```

设备路径：二进制`/userdata/xtapp/xt_camera`、`xt_radar`，日志`camera.log`、`xt_radar.log`；服务`/etc/init.d/S98xtnet`、`S99xtradar`、`S99xtcamera`。重复camera start有抢端口风险，维护时使用明确stop/restart并验证PID。

构建入口 `board/build.sh`，需可用的Linux交叉编译环境、cmake/make/g++-aarch64-linux-gnu。从项目挂载根运行：

```bash
bash board/build.sh
```

输出 `build/board/xt_camera`、`xt_radar`，依赖构建在`build/zenoh-aarch64`，FRAG_MAX_SIZE=300000。后续已在板端既有xtbuilder原生编译并验证，Windows WSL/Docker Desktop故障不再阻塞；没有重置它们。

当前`board/bin/`更新为本轮重新编译结果，旧版另存archive/board-pre-fix-20260831。板端备份在/userdata/xtapp/backup-before-jpeg-config-recovery-20260831。新部署流程先备份、临时文件校验，再替换并独立订阅，不把put=0当成验收。

本轮板端构建复现（xtbuilder挂载/userdata/xtapp到/work）：

```sh
docker start xtbuilder
docker exec xtbuilder sh -c 'CROSS= BUILD=/tmp/xtbuild JOBS=2 bash /work/release-20260831/board/build.sh'
docker exec xtbuilder sh -c 'ZSOURCE=/work/release-20260831/vendor/zenoh-pico ZBUILD=/tmp/xtbuild/zenoh-aarch64 bash /work/release-20260831/tests/run_board_unit.sh'
```

不要链接旧/work/zenoh-pico-main/build库（FRAG4096）。源码/头文件/静态库必须对应，缓存不匹配时build.sh会拒绝。生产配置在/userdata/xtapp/config.json；setting保存后重启对应服务，两个服务均读取此文件。config_file的按需触发与文件白名单见BOARD_FIXES。

## 6. 卡顿排查

先看/api/status的image age与seq，再看Foxglove/网页。image healthy而网页STALE，检查浏览器tab状态、内存/解码和HTTP；两者age一起升高，则向Zenoh和板端查。put=0只说明调用返回，不能证明订阅成功。

用独立audit_live短测比较Zenoh/WS接收间隔。旧版两者都出现约1秒间隔，当前已增加GET/首字节、队列、编码和put分阶段记录；查看camera.log的http_ms、queue_ms、pb_ms、put_ms和cap计数。不得靠降分辨率、重复旧帧或重新转码掩盖。

`runtime/gateway.log*` 轮转；stderr主要保存原生库异常输出。板端camera.log目前很大且未轮转，需另行处理。不要把完整抓包、相机样本或包含凭证的历史归档上传公开仓库。

## 7. 回滚与证据保护

`archive/pre-gateway-20260831.zip` 保存替换前关键PC启动/桥源码和相关板端源码快照；`archive/historical-root-20260831.zip` 保存406个历史根文件，逐个SHA256核对后才清除原位置。board/src现为修复后的源码，不再是旧版；旧板端原件另有本轮备份。

回滚PC时先停当前守护及其网关进程树，在独立临时目录展开备份检查，不要直接覆盖新证据；恢复旧启动链会重新引入旧卡顿/旧端口残留风险，不建议常规使用。当前任务设置的原XML另有保存。
相机第一帧、PB样本、逐帧CSV和JSON留在evidence。raw_data历史分片不自动清除；新记录仅清理自己的pointcloud子目录，不能当永久存档。
