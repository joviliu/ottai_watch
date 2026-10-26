# HyperOS 后台冻结排查

## 已确认的原因

本机 HyperOS 3 的 Greezer 曾在镜像应用退后台时冻结其进程。进程未退出，`BridgeService` 仍为 `isForeground=true`、类型 `connectedDevice`，常驻通知也保留；恢复 Activity 后 Greezer 解冻，约 33 ms 后积压的 Ottai 通知集中进入监听器。

因此，不能用“进程还在”或“通知还在”证明正在接收新读数。也不能只看手机收到后至 ACK 的耗时：通知本身可能已积压很久。要同时比较 `notificationAt`、`observedAt`、原始 `sourceAt` 和表端文件导出回执。

此前锁屏短时验证没有覆盖较长时间真正退到桌面后的厂商冻结。后续验证必须先按 Home，使镜像不再是前台任务，再锁屏。

## 本机设置

- 自启动已允许。
- 标准电池子页面中，“允许后台使用”开启、“无限制”选中、“优化”未选中。
- Android 用户电池优化白名单已包含 `com.example.glucosewatch6`。
- 厂商运行时 `Settings.System.MILLET_NO_RESTRICT_APP` 名单仅追加了镜像包，保留所有原有条目。

HyperOS 3 的标准页面可以用下面的公开设置入口打开，然后点“允许后台使用”的**文字区域**进入选择页面；右侧开关只是开关，不能代替核对“无限制”单选项：

```sh
adb -s SERIAL shell am start -a android.settings.VIEW_ADVANCED_POWER_USAGE_DETAIL -d package:com.example.glucosewatch6
adb -s SERIAL shell cmd deviceidle whitelist +com.example.glucosewatch6
```

第二条只为镜像增加 Android 应用级电池豁免。实测仅添加该项，在退到桌面并锁屏约 37 秒后仍被厂商 Greezer 冻结，不能把它等同于厂商冻结豁免。

`MILLET_NO_RESTRICT_APP` 是厂商运行时派生名单，可能被 PowerKeeper 重新生成；手动追加不是权威 `bgControl=noRestrict` 配置的替代品。不要用只含镜像包的字符串覆盖整份名单。当前固件的 PowerKeeper 配置 provider 要求签名权限，普通 shell 不能直接查询或修改，本项目不绕过该权限、不关闭全局冻结或 Doze。

重启、系统更新或其他省电策略变更后，应重新核对实际“无限制”选项与豁免状态，并复验自然更新。当前设置不构成未经验证的长期或重启后保证。

## 手机 0.1.11 的执行保障

0.1.11 / versionCode 12 不改变表端协议、0.1.8 RPK 或 0.1.10 表盘，已确认的布局与配色保持不变。

- 新读数及发送尝试为当前完整读数身份申请短时 `PARTIAL_WAKE_LOCK`，每次执行窗口至多 20 秒；持有同一身份时不续期。收到匹配当前完整 `frameKey` 的 `face_export` 后提前释放，服务停止时也释放。若超时仍未送达，后续重连或重新发送可再申请一次窗口，因此不是一个读数终身只允许 20 秒。
- 先正常发送，8 秒无当前身份的文件写入确认才自动唤起手表应用。60 秒唤起冷却只限制重复的同一完整身份；新测量时间或同时间的数值/趋势更正不被旧身份的冷却阻塞。
- 异步启动回调核对当前会话身份，过时回调不清理较新会话。监听器记录连接/断开并在断开时请求重绑；有新数据而桥接服务不在时尝试恢复前台服务，不能代替用户授予通知访问。

前台服务不会自动保持 CPU 唤醒；基于 `Handler` uptime 的延时任务也可能随深睡眠推迟。这个窗口用于保障新通知进入进程后的发送、8 秒兜底及导出回执，不能解冻已被厂商冻结的进程，仍需前述省电设置。没有新增秒级传感器轮询或全局保活。

## 历史证据的范围

0.1.8 的两轮短时锁屏自然更新完成了文件导出、ACK 与用户屏显确认，通知接收到 ACK 约 9.8/9.7 秒。这是短时连通性和自动返回基线；当时没有先确认 Home 后的 FGS 后台状态，不能据此证明真正退后台或长期休眠仍会更新。

本轮 0.1.10 复核在设置调整后，两轮通知进入监听器仅延迟约 5/10 ms；但第一轮没有 `FACE_WAKE`，在通知进入镜像约 40 秒后，经用户手动打开手表应用才导出，不能算自动成功。第二轮有自动唤起和约 9.8 秒文件回执。首轮漏唤起是否由 CPU 深睡眠延时或旧身份冷却造成未单独证实；0.1.11 分别补上这两处执行保障。

## 验证方法

1. 保持 Ottai 正常采集，不向手机或手表注入测试血糖。
2. 按 Home，确认镜像处于 FGS 后台状态，而非 TOP/TOP_SLEEPING；然后锁屏。
3. 至少等待两个新的 5 分钟自然周期，不打开镜像应用。
4. 核对每轮通知处理延迟 `observedAt - notificationAt`、完整读数身份，以及自动 `FACE_WAKE`、匹配的 `FACE_EXPORT`/ACK 和 CPU 窗口的申请与释放；若需要用户打开手表应用才导出，不算通过。
5. 检查 Greezer 在验证窗口内是否再次冻结该进程，以及运行时豁免是否仍存在。

USB 断开时日志仍留在手机；回读时必须检查时间差。若解锁后才批量补收，不能判为后台通过。

0.1.11 已覆盖安装，升级后运行时豁免仍在。先 Home 再锁屏的观察中，已取得一次同原始测量时间的自然趋势状态更正：通知处理约 13 ms，约 8 秒自动 `FACE_WAKE`，约 9.46 秒收到文件导出并提前释放 CPU 窗口，ACK 约 9.5 秒；期间未手动打开镜像，未观察到进程再次冻结。它证明这次后台执行、自动唤起和提前释放完成，不能计作一个新测量周期，也不是精确屏显延迟。

这一阶段上游 Ottai 的原始测量时间曾停滞，用户确认手机此前与传感器距离较远。恢复距离后，连接恢复的一条补传和随后两个相隔 5 分钟的正常自然测量均自动完成文件导出：

| 样本 | 通知处理 | 自动唤起 | 文件导出 / CPU 窗口提前释放 | 普通 ACK |
| --- | --- | --- | --- | --- |
| 连接恢复补传（不计正常周期） | 约 7 ms | 约 8.00 秒 | 约 9.71 秒 | 约 9.77 秒 |
| 第一轮正常自然测量 | 约 8 ms | 约 8.01 秒 | 约 9.63 秒 | 约 9.69 秒 |
| 第二轮正常自然测量 | 约 10 ms | 约 8.01 秒 | 约 9.61 秒 | 保留日志未见，不补写 |

两轮正常自然测量都有匹配当前完整身份的 `face_export`。后一轮普通 ACK 在保留日志中未见，因此记录为文件导出已确认、普通 ACK 未确认；不写成两轮普通 ACK 均已验证。通知到导出的耗时不是精确屏显延迟。

验证先 Home 并锁屏，随后手机另一个应用处于前台且屏幕已亮，镜像持续后台、进程未更换，没有新的 Greezer 冻结，运行时豁免仍在；不能称两轮全程关屏。用户未打开手表镜像，仅抬腕确认第一轮原始测量时间已显示且正常返回；第二轮屏显确认待回覆。两轮后台文件更新已完成，完整目视收尾仍待确认。

先核对 Ottai 自身是否有新的 `sourceAt`，再判断镜像投递。旧测量状态更正、连接恢复补传不能代替正常自然周期；本轮结果不证明重启后豁免耐久、长期稳定性、连续深睡眠或耗电。

## 来源与边界

根因以本机 Greezer 日志和服务状态为证据。小米官方也要求 Mi Fitness 检查无限制、自启动及后台锁定，但最近任务锁定主要避免被一键清理，不能代替实际运行验证：[Mi Fitness 后台说明](https://www.mi.com/uk/support/faq/details/KA-592820/)。

厂商运行时名单与权威配置的区别参见作者从其固件提取代码并验证的[原始调查](https://github.com/dingwen07/hyperos-fcm-fix/blob/main/docs/xiaomi-hyperos-gms-fcm-greezer-investigation.md)和[重写时序调查](https://github.com/dingwen07/hyperos-fcm-fix/blob/main/docs/xiaomi-millet-no-restrict-app-rewrite-investigation.md)。这些是具体固件的逆向证据，不能假定其他版本的私有接口兼容。

Android 行为依据：[Handler 延时使用 uptime，深睡眠增加执行延迟](https://developer.android.com/reference/android/os/Handler#postDelayed(java.lang.Runnable,%20long))、[WakeLock 超时与主动释放](https://developer.android.com/reference/android/os/PowerManager.WakeLock)、[前台服务本身不保持 CPU 唤醒](https://android-developers.googleblog.com/2026/03/battery-technical-quality-enforcement.html)。这些平台规则解释执行窗口的用途，实际厂商冻结仍以本机日志为准。
