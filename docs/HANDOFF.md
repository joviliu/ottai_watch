# 接续任务入口

2026-10-30 新检查：用户反馈连续两天相同时段颜色相同。已确认旧源码有日期种子，但旧大整数混合在真实 float32 Lua 中退化为每日固定两组，int32 也与桌面不同；已修复并准备三款 [0.1.18](../releases/0.1.18/README.md)，低精度回归/原 UI 与资源测试通过。**尚未真机覆盖，当前设备仍是下表版本；本表实际 Lua 编译配置未读取，现场根因仍需观察。** 本轮没有操作手机或换客户端，保留官方 3.59.2。原 2026-10-29 完成记录如下。

2026-10-29。代码与表盘 UI 已定稿、已推送并通过 CI；按用户最后要求，手机已切回原国行官方小米运动健康 3.59.2。当前官方版下两轮非充电锁屏新测量已自动更新，用户仅抬腕确认最后更新时间与 Poiret One 表盘正常；全部收尾完成。不要按历史修改版状态继续操作。

## 当前设备与制品

| 组件 | 当前版本与状态 |
| --- | --- |
| 手机蓝牙网关 | 官方 `com.mi.health` 3.59.2/code359002；修改版 `com.xiaomi.wearable` 已卸载 |
| 手机血糖镜像 | `com.example.glucosewatch6` 0.1.11/code12，本次不升级、不清数据 |
| 手表血糖镜像 | RPK 0.1.12/code13，3.9/7.8 两条无圆点细线已获用户确认 |
| Ultra | 0.1.14，ID `8670260101`；用户确认不再改动 |
| Signal | 0.1.17，ID `8670260102`；Poiret One 原字形及布局已获用户确认 |
| Meridian | 0.1.16，ID `8670260103`；极简指标、实际指针配色和长按切换已获用户确认 |
| 临时表盘安装器 | 0.1.5 已卸载，已查询确认不存在；其手机端私有输入随卸载删除 |

最新功能源码提交 `fb7e26cd80ffcde2f4a7348a0ca8043046120d9d`，CI [40845387617](https://github.com/joviliu/ottai_watch/actions/runs/40845387617) success。三个表盘 ID 独立，可切换，共用同一真实数据文件与 RPK，无需换手机镜像。

直接取用：手机 [0.1.11](../releases/0.1.11/README.md)、RPK [watch-0.1.12](../releases/watch-0.1.12/README.md)、Ultra [0.1.14](../releases/0.1.14/README.md)、Meridian [0.1.16](../releases/0.1.16/README.md)、Signal [0.1.17](../releases/0.1.17/README.md)。各目录先核对 SHA256SUMS，不重复安装旧字体/透明窗口试验。

## 本轮验收与边界

- 用户逐款确认可见、布局无误；Signal 当前为指定 Poiret One 原字体，等比缩放，圆润 0/8 不纵向拉长；48px 血糖栏与 GLUCOSE 同行。Meridian 底部固定浅灰血糖替换原心率，使用同一 MiSans-Regular 28px；箭头为淡绿/淡黄/淡红，过期或无合法数据用暗灰，不显示更新时间/OLD，也不订阅心率。Ultra 保持原样。
- 0.1.15 的 image recolor 在真机没有生效，不能把那次本地模拟器通过当作实际随机色通过。已修复：Signal 用 32 组预着色数字，Meridian 用原生 bg_color 对象指针。用户确认两款当前时段实际颜色正常；32 组可达、04/11/15/19、同段稳定、相邻不重复、午夜与休眠恢复均通过代码测试。尚未持续等待真实跨切换时点或多日耐久。
- 换官方前，APK 0.1.11 + RPK 0.1.12 + Meridian 0.1.15 + 修改版 3.33.6i，正式非充电锁屏两轮新测量已通过：原始时间均晚于起点且相差 300000ms，自动完整身份导出约 9.805/9.478 秒，ACK 约 9.833/9.501 秒；45 秒采样均关屏、非充电、两端 FGS、两项豁免保持，无新增冻结。此历史结果与下述还原官方后的最终验收分别记录。
- 当前官方还原：先由用户完成修改版健康同步，保留并校验两版回退 APK；卸载修改版、安装原官方 3.59.2，完成首次引导。用户确认官方设备页手表已连接、厂商无限制已选；原官方/镜像 NLS、两应用默认启用、FGS 及厂商/Android 两项豁免已核对。镜像已实际绑定官方 WearableXmsService，重建连接后已取得文件导出与 ACK。最终锁屏非充电验证已通过：两条源测量及通知均晚于起点，源时间相差 300000ms，每条一个元数据事件；自动导出约 9.684/9.664 秒、ACK 9.715/9.693 秒，CPU 提前释放。全部 45 秒采样均关屏、非充电、两应用 FGS、两项豁免保持，无新增冻结。用户没有手动打开两端镜像，仅抬腕确认最后更新时间已更新、正常停留 Signal 0.1.17 表盘。详见 [官方验收](official-mifit-compatibility.md)。
- 已确认修改版和临时安装器均不存在；本次手机 UI 临时快照与启动 dex 已清理。手表未解绑/重置，三款表盘及两端镜像数据均保留。没有重新检查重启、AOD、多日稳定性或长期耗电；用户已停止旧的夜间电量归因调查，不继续该项调查。

## 日常更新与恢复契约

Ottai 通知约每 5 分钟一次。手机镜像监听真实通知并发帧；8 秒没有当前完整身份的文件导出确认时，才短暂自动唤起手表应用，写双槽文件后返回原表盘。进入时保留旧数值和原始时间，不显示伪造新鲜值。无需手动打开手表应用，也不需要 xDrip/WatchDrip。

`frameKey = sourceAt | 规范数值 | 原始趋势`；同时间更正不被旧 ACK 清除。RPK 串行发布最新帧，旧完成不得越过新帧确认/退出。手机短时 CPU 窗口最多 20 秒，匹配导出后提前释放；同身份 60 秒冷却不阻挡新测量。Lua 创建/亮屏/恢复时读文件，可见期间每 15 秒检查小文件，息屏暂停，无新增无线或传感器轮询。

官方当前通知监听为 `com.mi.health/com.xiaomi.fitness.notify.NotifySyncService`，镜像为 `com.example.glucosewatch6/com.example.glucosewatch6.OttaiMetadataListener`。修改版组件名不同，恢复时不能混用。HyperOS 必须核对厂商“电量详情 → 省电策略 → 无限制”；Android 标准页允许后台不等价。常驻通知、SDK accepted、旧缓存回执不能单独证明后台新周期通过。

## 再次开发/安装

先读 [安装](install.md)、[后台策略](background-running.md)、[表盘](../watchface/README.md)、[数据契约](protocol.md)、[签名](signing.md)。需要 Node.js、Python/Pillow/Lupa、JDK17+ 和 Android35 工具链。改 APK/RPK 前须安全迁移原 `.sign/`，不能随意生成新证书覆盖已有安装；密钥不进 Git。

```sh
sh tools/test.sh
python watchface/test_frame.py
python watchface/test_ui.py
python watchface/build.py --variant all
python watchface/test_assets.py
```

表盘用 [SPP 安装器](../tools/spp-installer/README.md) 及自己的合法配对凭据；输入经 stdin 写应用私有文件，再回读核对 SHA256。只 replace 当前 BIN 对应 ID，删除后独立查询确认，保留另外两款。上一操作 DISCONNECTED 后再启动新操作。结束恢复实际客户端与镜像的原授权、启用/运行状态，再卸载安装器，确认新通知/文件回执及表盘当前读数。

官方版的日常同步已在当前 APK 0.1.11 + RPK 0.1.12 + Signal 0.1.17 组合验证；本轮官方环境下的表盘上传曾 Broken pipe，根因未定，不能断言官方禁止安装。修改版对照完成了三款上传与 RPK 覆盖；官方 RPK 侧载入口尚未验。不要为日常运行再次换修改版；确需侧载对照时先同步并保留回退，最后按用户要求还原官方。

运行时日志、健康数据、账号、设备标识、回退 APK 与配对密钥只留在仓库外的本机私密目录，不上传。历史验收见 [validation](validation.md)、[官方兼容性](official-mifit-compatibility.md) 及各版本发布目录，不能把旧版结果迁作新版结果。
