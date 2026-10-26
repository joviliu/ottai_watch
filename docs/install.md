# 安装与排查

## 依赖

手机保留 Ottai、「血糖镜像」和当前可用的 Mi Fitness mod。当前桥接方案不需要 xDrip 或手机 WatchDrip；实机上这两个旧应用已停用并保留数据。手表旧 WatchDrip 快应用也不参与本方案。

Mi Fitness 是当前蓝牙和 RPK 安装通道，不能直接删掉。原国行「小米运动健康」与本次 mod 曾发生 Android 共享权限冲突，原版已在用户同意且先同步数据后替换。回退原版需先同步并重新处理登录/绑定，仓库不分发任何第三方 APK。

## 手机

最新 UI 更新的手机 APK 为 0.1.10 / versionCode 11，见 [0.1.10 发布目录](../releases/0.1.10/README.md)，本轮只覆盖当前单款表盘，用户已确认最终布局正常，正常重启后通知图标也已确认正确；手表 RPK 功能未变，继续使用 [0.1.8 发布目录](../releases/0.1.8/README.md) 的 0.1.8 / versionCode 9。两个目录分别核对 `SHA256SUMS` 后安装；两端包名、证书须匹配，版本号可以不同：

```sh
adb devices
adb -s SERIAL install -r releases/0.1.10/glucose-watch6-0.1.10.apk
adb -s SERIAL shell am start -n com.example.glucosewatch6/.MainActivity
```

在手机授予通知访问、通知显示、蓝牙附近设备权限；允许后台运行/自启动并取消电池限制。首次授予侧载应用通知访问可能需要在应用信息菜单允许「受限设置」。Ottai 必须保持原有正常采集和通知。密码、验证码仅由用户在手机输入。

## 手表

先确认 Mi Fitness 已连接手表。若其调试入口可直接使用，进入「我 → 关于 → Debug → Third-Party Apps」，包名填 `com.example.glucosewatch6`，Install third app 选择 RPK。

本次 mod 的入口不容易通过普通菜单打开，可使用已有的辅助脚本：

```sh
. .toolchain/android.env
python3 tools/open_installer.py --serial SERIAL --rpk releases/0.1.8/glucose-watch6-0.1.8.rpk
```

该脚本把 RPK 推到手机 Download，打开 Mi Fitness 的内部安装页；仍需在手机选择包名、文件并确认安装。它清理该应用的 UI 返回栈，不清除应用数据，不等于安装已成功。此入口依赖当前 mod 内部类，其他版本可能不兼容。

安装后查看 Mi Fitness `handleInstallResult` 的包名、版本号和成功码；再在手表打开「血糖镜像」，核对数值、趋势和测量时间。`发送文件成功` 不足以证明安装成功。

## 容易踩的坑

- APK / RPK 包名与签名必须匹配，见 signing.md。
- Mi Fitness 页面复用旧任务时可能不展示 Debug；辅助脚本使用 NEW_TASK + CLEAR_TASK。
- 部分 Mi Fitness 控件忽略 ADB 零时长 tap；可用同坐标 150 ms swipe 模拟短按。每次先读新 UI 层级，键盘会移动输入框。
- 多显示/多输入环境中必须指定目标显示：`adb shell input touchscreen -d 0 swipe X Y X Y 150`。本次实机上不指定 `-d 0` 曾出现命令成功但主屏无变化；先读取显示与焦点再操作。
- 手机安全锁屏只能由用户解锁，不要关闭锁屏来方便自动化。
- 手表打开时看到旧数值，数秒后变化属于缓存后同步；观察 `sourceAt`，不要只比较数字。
- 不要为了后台刷新声明无关音频或定位权限。

## Lua 表盘开发安装

0.1.10 本轮只提供 Ottai Ultra，ID `8670260101`，按用户要求覆盖当前样式。[layout.json](../watchface/layout.json) 是唯一参数源：时钟 6×14/90×232，y=68..300；稀疏 5×7 血糖 y=352 居中，左侧亮时间 y=365、右趋势 y=353。输出为 `watchface/build/ottai-minimal-watch6.bin` 和同名 `.zip`。最终覆盖已完成，用户确认布局合适、显示正常。

将来不同风格可以用独立 ID 并存，共用同一 RPK 和数据文件；本轮不发布或安装第二款，预留 ID 不代表已有第二款可用。

构建步骤见 [watchface/README.md](../watchface/README.md)。本地成功生成 BIN 和开发安装 ZIP 后，可使用：

```sh
. .toolchain/android.env
python3 tools/open_installer.py --serial SERIAL --watchface watchface/build/ottai-minimal-watch6.zip
```

此命令推送 ZIP 并打开 `FaceDesignerFragment`。当前 mod 已完成解压和工程文件检查，但其强制签名授权 `designer_license` 请求返回 HTTP 404，此入口未完成安装。不要把解压成功等同安装成功；保留原表盘作为回退。若继续使用此入口，需要解决正常的开发授权或服务兼容问题；不要强制修改不可点击的签名选项。

本次已通过[临时本地 SPP 安装器](../tools/spp-installer/README.md)完成认证、100% 上传及断开，修正 Lua 入口后用户确认表盘正常绘制。它需要用户自己手表的有效配对密钥；不能使用参考项目预填的默认密钥，任何密钥均不提交 Git、不写入公开日志。无需重置或解除现有配对。安装器使用 0.1.4 / code 5，白名单允许当前 `8670260101` 和未来预留 `8670260102`；本轮只替换前者。`replace` 只删除当前 BIN 对应目标，独立查询确认删除后重装，不影响其他 ID。再次执行 `am start -S` 前须等上一轮 `DISCONNECTED`。

0.1.10 手机 APK 与现有 0.1.8 手表 RPK 保持相同包名、证书和数据协议，无需因图标变动重新安装相同 RPK；新环境仍需安装两端。“表盘自动同步”新安装默认关闭。0.1.8 基线验证时已开启，并观察到后台 8 秒未确认后自动唤起、文件导出和 ACK，无需用户手动打开表端。用户已确认自动返回点阵表盘及读数显示，手机锁屏后连续两轮自然更新均已完成导出与 ACK；用户确认最新一轮数值、水平趋势、原始时间显示正确且正常返回，未报告明显闪屏或卡住，开发版基本验收通过，详见[验证记录](validation.md)。该策略必要时短暂唤起同步页后返回，不是常驻后台能力。

安装器运行前暂停应用时，优先避免改变其启用状态。实测 `disable-user` 可清除两应用原通知访问；若使用过，结束后必须恢复原运行状态，恢复此前已授权的镜像通知监听与 Mi Fitness `NotifySyncService`，重连后核对最新 Ottai 数据确实已进入镜像。手机镜像启动时会请求重新绑定监听，但不会自动授予被撤销的通知访问。详细恢复步骤见安装器 README。

本轮临时 SPP 安装器 0.1.4 已卸载成功，手机端私有凭据随卸载清除。正常重启后恢复默认启用状态和原通知监听，随后自然新通知在未手动打开表端的情况下完成文件导出及 ACK，通知到 ACK 约 9.8 秒。恢复缓存通知的回执不计入这个自然周期延迟。安装器不参与日常更新。

恢复检查必须在重启后再次核对：实际查询两应用处于原来的默认启用状态、原通知访问仍在且监听已绑定，并确认最新 Ottai 自然通知进入镜像。仅有 `pm default-state` 成功输出不够；本轮曾在重启后再次发现 `disabled-user`，原因未确定，已重新恢复。升级后的旧通知图标本轮通过正常重启后重新加载得到正确显示，无需清除应用数据。

追加动态配色只更新同 ID 表盘，不升级手机 0.1.10 或 RPK 0.1.8，布局不变。数值与趋势按用户自定义显示分段变色：3.9–7.8（含两端）紫色，大于 7.8 至 12.0（含 12.0）黄色，其余有效值红色；旧数据仍有 OLD 并在对应色系变暗。新增配色版已通过 SPP 覆盖、恢复原运行状态与通知监听，并再次卸载临时安装器；三色与边界为桌面验证，用户目视确认来自此前同布局版本。详见[表盘颜色规则](../watchface/README.md#用户自定义显示颜色)。
