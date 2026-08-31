# 改动与清理记录

## 后续板端修复

用户追加授权后，已修改并部署board/src/xt_camera.cpp、xt_radar.cpp及新增的device_config.hpp、zenoh_config.hpp、request_parser.hpp、snapshot_client.hpp。新增libcurl/json依赖、原生构建/备份部署脚本、带ASan/UBSan的板端单元、配置及故障注入测试。完整说明和本次SHA见[BOARD_FIXES](BOARD_FIXES.md)。

继续排查后再修改pc/gateway.py：沉默时保留Zenoh会话与订阅，底层自动重连；增加耗时诊断。xt_radar新增异步控制事件记录、publish_queue.hpp有界发布队列，将网络发送与UDP采集解耦。根据用户将全部设备接到交换机的实际拓扑，新增持久radar_network及--network管理入口，设置eth1/.250并实机读回UDP目标。没有改变相机编码、图像文件内容、雷达坐标或抽掉有效点；IMU仅移出原发送调用，不改业务解析。

新增/更新tests/test_gateway.py、test_recovery.py、board_unit.cpp、radar_zenoh_fault.sh与旧eth0故障脚本的拓扑保护。最后18项配置检查、100/1000帧及210秒双流接收、12秒雷达发送阻断、HTTP原始JPEG检查均有独立evidence。当前清单board-switch-manifest-20260831.json；保留此前7分钟失败和改线/未供电窗口，不用最终短测覆盖历史失败。30分钟验收未执行。

下面的“本轮”“没有修改”和旧哈希表保留为**此前PC整理阶段**的历史记录，不再代表当前板端未修改。PC旧板端快照在archive/board-pre-fix-20260831，板端原件在一次性backup-before-jpeg-config-recovery-20260831。没有删除旧证据，也没有改IMU业务或重启整板。

## 本轮实际修改

1. 新增`pc/gateway.py`：使用官方Zenoh Python和Foxglove SDK，把相机与点云放入同一8766连接。回调入队、处理线程独立；JPEG不重编、每个收到的点均适配显示。
2. 新增`pc/viewer.html`：内存最新JPEG长轮询，按新帧ID计数，有超时和过期提示，移除旧“每帧落盘再读文件”的显示依赖。
3. 新增`pc/recorder.py`：异步原始点云记录、有限队列、错误计数，保留原先最近5分钟原始点云能力。完整分片轮转尚未另做长期验收。
4. 替换`start_yunke.ps1`：只守护一个本机网关进程树；读取配置端口；不再重置网卡或定时SSH重启板端雷达。修正Windows venv子进程退出处理。
5. 修正项目计划任务设置：电池运行允许、取消72小时限制、失败重试/补启动。原XML和新XML均保存。
6. 新增协议定义/生成代码、固定依赖、setup_pc.ps1、独立真实订阅测试、模拟断流、单元与守护测试、只读命令检查、交付链接/HTTP原消息/磁盘记录检查。
7. 在本机Foxglove设置正确frame/topic，打开相机与点云双面板、关闭巨大坐标标签、移除无内容的Raw面板。布局导出未完成，用户中止界面操作后不再操作。
8. 整理项目说明、协议审查、验收、运维、交接与本记录。

## 没有修改

- **没有修改或部署板端C++代码/二进制，也没有触发板子重启。**板端C++仅在PC项目中迁入board/src，启动脚本迁入board/init。
- 交付前发现雷达源停止出帧后，执行过一次`S99xtradar restart`（服务级，PID4755→4850），恢复数据；这不等于已修复根因或板端自动恢复。相机服务未重启。
- 没有把JPEG切换回H264，没有相机转码、重编码、分辨率切换、JPEG字节修改，也没有新增伪造TF/外参。
- 没有改IMU，没有将setting/config_file/硬件热插拔问题伪装成已修复。
- 没有继续30分钟测试，没有重置Docker/WSL或改变其他项目的进程、数据与网络。

## 清理结果

根目录原有434个文件，406个历史脚本/日志/抓包/EXE/文档/安装包压缩归档后从原位置移除；17份PDF原件集中到docs/reference；板端7个文件迁入board；留下根目录4个安装/启动/依赖入口，另新增README/HANDOFF/CODEX_AUDIT文档。

旧链路`z_sub_jpeg.exe`、`foxglove_bridge.exe`、`mjpeg_server.py`、旧启动脚本不再位于运行入口。历史源码没有永久丢弃，记录逐项路径/大小/哈希在`archive/cleanup-manifest-20260831.json`。

FFmpeg目录、旧Windows构建缓存和空frames目录最终采取**移入archive/obsolete-*保留**，不是声称彻底删除；它们不参与新运行/构建。一次性整理脚本记录的是原计划，manifest中的`archived_generated_directories_actual`为最终事实。旧SDK镜像迁移遇只读文件，余下文件保存在archive/vendor-sdk-mirror的同名子目录，未丢弃；它不是新构建依赖，权威参考为vendor/xtsdk。

原始文件的批量归档经过解压流SHA256逐个验证；没有git仓库可作回滚，因此保留ZIP和资料。raw_data历史记录与evidence不做清空。归档仍占磁盘空间，框架精简不等于宣称归档占用已回收。

## 固件快照SHA256

| 文件 | SHA256 |
| --- | --- |
| board/bin/xt_camera | 99993F87D0E38FB01F48CF1B9881E716196B075666C195ADCF1F70728F2A1ACA |
| board/bin/xt_radar | E3DF3969A2E1C5A627BBA88651920D0BEEE2138887730D5414AAFDB7F1663882 |
| board/src/xt_camera.cpp | 904E2A3FF1781CFE1E0E31984D2AD730D1471650E8A8FCA06384EE2025272513 |
| board/src/xt_radar.cpp | F29518FBF634C9F30DE5A16F373E2B47234FA5F09E87BE2C294E9FCE40EB0318 |

两个二进制SHA与本轮SSH读取的板端文件一致。新board/build.sh仅适应目录整理，未在正常容器中完成复编验证，不能拿它作可复现构建通过证明。
