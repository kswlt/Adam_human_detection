# 当前交接入口

最后更新：2026-08-31，Windows工作目录`C:\Users\Admin\Desktop\yunke`。

**2026-09-01相机双格式已部署**：甲方最新确认`SettingRequest.image_format`为0不修改、1 H264、2 JPEG；实际`ImageMsg.format`分别为3和2。MC800S MainStream实测为原生H264 High 1920x1080/10Hz/4096kbps/GOP20，板端使用RTSP/TCP加ffmpeg `-c:v copy`，一条消息一个Annex-B access unit；JPEG仍是原生snapshot完整文件。H264 1800帧3分钟10.010749Hz、JPEG1000帧9.939858Hz，均零协议错误/seq缺口，H264从首个IDR起1781帧被标准解码器全部解码。JPEG/H264分别做过整板重启持久化。完整证据和风险见[相机双格式交付记录](docs/CAMERA_DUAL_FORMAT_20260901.md)。

当前最终留在JPEG，`config.json`为image_format2/image_fps10/h264_gop20/h264_bitrate4；浏览器`/latest.jpg`实测1920x1080、网关healthy约10Hz。最终板端SHA：xt_camera `6601b46c...d13808b`，xt_radar `780e9710...5ff4e2`。相机setting重启已改为关闭继承fd后fork/exec，隔离复测中xt_radar PID1290不变，7447/7448分别只由radar/camera持有。PC网关按任务约束仍只显示JPEG，H264通过独立订阅和FFmpeg验证；雷达源当前无有效帧，不能把“进程未重启”扩写为点云连续通过。

**2026-09-01最新异常覆盖**：雷达当前处于反复停流/固件重启循环，Foxglove怪点云来自真实收到的异常源数据，不是显示器造点。完整当前日志7303个温度抽样中3204个sensor读数超出-40..125°C（范围-293.70..310.95°C），累计735条`sensor fail 1 to reboot`、772个新停流周期并都曾恢复；devstate帧尾仍全为3，说明该字段不足以识别故障。50帧实测139453点，距离中位8.697m、P95 36.831m、最大50.000m，明显超出M60室内0.3-20m标称范围，强度P50=229/P95=255。当前数据不可作为可靠测距。证据`evidence/radar-weird-full-20260901.log`、`current-weird-pointcloud-range-20260901.json`。未改源码/参数/颜色。

Foxglove通道使用固定`frame_id=lidar`和单位姿态，无IMU/TF；转动雷达时环境会在雷达坐标中变化，不会稳定到世界坐标。源停流时Foxglove保留最后一帧，因此遮挡后仍看到点不等于仍收到新点。PC没有删点或距离裁剪，异常0-50m数据原样适配显示。

自启动配置存在：板端rcS运行S98xtnet/S99xtcamera/S99xtradar，当前脚本和二进制存在；PC `YunKeAutostart` BootTrigger/StartWhenAvailable/无限时长且Running。两个同启动时刻python进程是Windows venv redirector和实际解释器，不是两个独立网关。整板冷启动仍没有本轮正式验收，不能仅凭配置称百分百通过。外部风扇是否共用雷达电源待用户答复；静电只有触碰裸针/未接地导体或带电插拔时才是候选，单纯遮挡光学窗不能解释持续错误温度/重启。

**当前状态（用户再次给雷达重新上电后）**：雷达.101已恢复，原xt_radar PID14084自动接回，未重启板端服务；ping3/3、TCP7787建立，UDP目标读回.250:7687。新60秒直接/WS点云各300帧、约5Hz，最大318.219/335.238ms，seq/解析/stamp错误0，温度末次45.74°C，sensor fail旧计数10未增。证据 `evidence/radar-second-powercycle-60s-20260831/summary.json`。下述19:47离线为历史故障，不能当作现在仍离线；但本次恢复也不意味着根因已查清。未改代码、参数或颜色，测试已结束。

**最新现场状态（约19:47）**：散热短测之后雷达再次离线，最后收帧约19:37:55，已持续9分钟以上；停流前最后温度54.22°C，旧sensor fail计数10未增加。PC和板端ping失败，绑定实体PC地址的TCP7787连接超时，板端ARP3次0响应；相机正常、两生产进程未退出。厂家GUI曾使用198.18.0.1连接且不断命令超时，但当前板端绕过该路径也不可达，不可仅归咎于代理或过热。待用户检查雷达供电/交换机端口/IP改动，详见断流调查末节。本轮未改代码、参数或颜色。

最新故障覆盖说明：210 秒短测后又发生雷达自然断流。当前已查到 UDP 停止、设备报告 `sensor fail 1 to reboot`，首次故障前传感器读数最高 87.47°C，但后续约 58.6°C 也有故障，尚不能确诊过热保护。详见 [雷达断流调查](docs/RADAR_FREEZE_INVESTIGATION.md)。本次仅只读检查与记录，未修改/部署运行代码、未改颜色、未主动启停或复位；不能声称长期稳定已通过。

用户添加外部散热后完成 180 秒短测：sensor 54.04→49.55°C，断流/故障 trace 累计仍为 8/10、没有新增；直接雷达 900 帧 4.999873Hz、最大 231.597ms，Foxglove 点云数据流最大 241.626ms，解析/seq/stamp 错误 0。证据 `evidence/radar-cooling-180s-20260831/` 及 `radar-cooling-temperature-180s-20260831.txt`。正常服务继续运行，短测已结束，30 分钟仍暂缓。散热前已自行恢复，不能把此轮无故障当作过热原因已确诊。
旧的本文件及system_handoff.md/codex_prompt.md已保存在`archive/historical-root-20260831.zip`，只作历史记录，以本版为准。

## 先读

1. [README.md](README.md)：交付入口、运行路径与目录。
2. [docs/PROTOCOL_AUDIT.md](docs/PROTOCOL_AUDIT.md)：不能忽略的协议与源码风险。
3. [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md)：真实通过范围与暂缓事项。
4. [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)：启动、构建限制与回滚。
5. [docs/CHANGES.md](docs/CHANGES.md)：本轮所有改动和清理边界。

## 当前运行

- RK3562板端`.250`，相机`.123`，雷达`.101`。用户于本轮将路由器更换为交换机，雷达也位于交换机侧；eth0无链路，板端从eth1访问雷达。固定地址保持不变。板端SSH root，固定指纹见部署文档。
- 图像：7448，`active/LX2601F10001/image`，原生1920×1080 JPEG、ImageMsgArray长度1、format2。
- 雷达：7447，`active/LX2601F10001/pointcloud`，LidarPointMsgArray长度1、scaler1000。
- PC统一网关：`pc.gateway`，HTTP8080、Foxglove8766。YunKeAutostart计划任务运行并守护，网卡1Gbps。
- Foxglove已看见两路真实画面；显示帧lidar。原始JPEG与点云在独立WS验证中内容一致，无96点截断。没有已验证的布局JSON导出。
- PC原始点云异步记录在raw_data/pointcloud，新日志runtime/gateway.log轮转。

## 不可误报

旧版1000帧图像9.8239Hz、点云4.7257Hz，另有982.5ms间隔。这是修复前基线，不能当作当前版本测试。本轮重新编译并部署板端，见[BOARD_FIXES](docs/BOARD_FIXES.md)及其中新测试结果；不能把短测结果说成长稳保证。
30分钟验收按用户要求已停止；不自动续跑。IMU不修。当前格式通过不意味着全协议通过。

已补config_file、setting原子持久化/错误码/图像真实配置回读、协议结构的zenoh配置、运行后雷达恢复。FrameInfo/UDP边界、工厂SN文件覆写、相机HTTP总期限/关闭连接/SIGPIPE也已修。物理拔插、真实整机开机、完整标定外参、板端日志轮转/进程退出守护尚未全项完成。
雷达另修正cmd19端口字节序（7687应发07 1E），已实机读回192.168.0.179:7687，启动无需先复位。撤回早期“setdest必须在reset前”的固件推断。网口恢复会丢失eth0专用主机路由，驱动只修这一条；正常测量不额外发cmd0，断网连接失败也不累计为需要复位的测量失败。
PC累计计数包含旧版故障、部署回滚和测试造成的中断/序号重置，不能清零掩盖。新版本的独立窗口另存evidence，不把新窗口零错误外推到整个会话。

## 本轮修改与下一步

本轮明确修改并部署board/src和板端二进制，也修改pc/gateway.py：数据源沉默时保留订阅，让Zenoh恢复TCP连接；仅会话确实关闭或异常才重建。新增处理/SDK发布/队列/HTTP事件循环耗时诊断。相机编码配置未变。旧板端二进制备份在PC的archive/board-pre-fix-20260831，以及板端/userdata/xtapp/backup-before-jpeg-config-recovery-20260831。

保持MC800S原生1080p JPEG，并新增相机原生H264直通；两路都不转码/不降清晰度。共享配置在/userdata/xtapp/config.json，图像setting保存后仅重启相机服务生效。config_file发送config.json及真实lidar_intrinsics.json，没有伪造camera-lidar外参。
构建用板端原有xtbuilder及项目vendor/zenoh-pico，输出容器/tmp/xtbuild。曾误用板端旧库缓存（FRAG4096）导致一次发布验收失败，已回滚后用项目源码FRAG300000重建并恢复；构建入口现会拒绝该旧缓存。不要再链接/userdata/xtapp/zenoh-pico-main/build。Windows WSL/Docker没有重置。

相机源端计时与雷达时钟epoch不同；Foxglove只使用PC接收时刻作显示，原消息stamp保留。必须补测曝光/传输延迟才能声称端到端低延迟。

## 继续验证时的现场变化

- fda833e版本7分钟测试不能判通过：原生图像9.9715Hz/最大296ms，但雷达中断，Foxglove图像最大间隔2078ms。完整失败证据见evidence/board-release-steady-20260831/，不能用前1000帧正常段替代整轮结果。
- PC保留订阅修改后，隔离测试与90秒真实双通道测试通过，详见BOARD_FIXES；不将短测外推为长期稳定。原Zenoh Python close/open释放GIL，不再沿用“close持有GIL造成停顿”的未经证实推断。
- 用户真实给雷达重新供电后，原xt_radar进程13496自动恢复；随后80秒400帧5.000051Hz、最大211.542ms，解析/seq/stamp错误0。测试目录after-physical-powercycle-20260831。当时相机0帧，用户随后确认相机未供电，不是解析或网页故障。
- 相机补电及切换交换机后，原xt_camera进程11631自动恢复1920x1080约10Hz；PC两路reconnects仍为0（保留订阅自动恢复）。实际断电/恢复时刻未统一采样，不能据此报告精确恢复耗时。整板断电持久性与30分钟验收仍未做。

## 最终交换机版本

已部署雷达97b843f5，PID14084；相机仍54de65ff，PID11631。当前哈希清单为evidence/board-switch-manifest-20260831.json（board-release-manifest是此前版本，勿混用）。新增发布队列publish_queue.hpp及radar_network持久字段，读取配置后真实确认UDP目标192.168.0.250:7687。工厂文件SHA不变。

12秒只阻断雷达Zenoh到PC的发送测试：实际put阻塞2471ms，UDP采集持续、无复位、两服务PID不变；解除规则后自动恢复。直接点云最大间隔14.023秒，故障窗口seq缺69帧，板端expired=9、put_errors=1，保留这些计数。直接及Foxglove图像最大约231ms、无500ms停顿，内容比对0不一致。证据switch-publish-fault-20260831与对应console；不能将这轮故障数据当正常5Hz/无损测试。

新配置/文件通道18项通过，config.json完整传递radar_network且字节与磁盘一致。HTTP100帧原始ImageMsgArray/JPEG哈希/解码通过，20条上限内实际检查15条完整原始点云记录。证据switch-config-final-20260831.json、switch-http-delivery-20260831.json。防火墙测试规则已清除，xtbuilder已停止。

最终210秒无故障注入窗口switch-final-1000-20260831：相机2079帧9.895121Hz/最大238.178ms；雷达1050帧5.002429Hz/最大323.751ms。两路接收seq缺口/解析/时间戳错误0，JPEG解码错误0；Foxglove图像最大255.983ms、点云最大326.229ms，均无500ms以上间隔，有效内部内容比对0不一致。详细100/1000帧及P50/P95/P99见BOARD_FIXES。不能将接收seq无缺口等同于每个计划采集时刻均成功，也不能声称严格10Hz或长期稳定通过。
