# 安装与排查

## 依赖

手机保留 Ottai、「血糖镜像」和当前可用的 Mi Fitness mod。当前桥接方案不需要 xDrip 或手机 WatchDrip；实机上这两个旧应用已停用并保留数据。手表旧 WatchDrip 快应用也不参与本方案。

Mi Fitness 是当前蓝牙和 RPK 安装通道，不能直接删掉。原国行「小米运动健康」与本次 mod 曾发生 Android 共享权限冲突，原版已在用户同意且先同步数据后替换。回退原版需先同步并重新处理登录/绑定，仓库不分发任何第三方 APK。

## 手机

```sh
adb devices
adb -s SERIAL install -r releases/0.1.4/glucose-watch6-0.1.4.apk
adb -s SERIAL shell am start -n com.example.glucosewatch6/.MainActivity
```

在手机授予通知访问、通知显示、蓝牙附近设备权限；允许后台运行/自启动并取消电池限制。首次授予侧载应用通知访问可能需要在应用信息菜单允许「受限设置」。Ottai 必须保持原有正常采集和通知。密码、验证码仅由用户在手机输入。

## 手表

先确认 Mi Fitness 已连接手表。若其调试入口可直接使用，进入「我 → 关于 → Debug → Third-Party Apps」，包名填 `com.example.glucosewatch6`，Install third app 选择 RPK。

本次 mod 的入口不容易通过普通菜单打开，可使用已有的辅助脚本：

```sh
. .toolchain/android.env
python3 tools/open_installer.py --serial SERIAL --rpk releases/0.1.4/glucose-watch6-0.1.4.rpk
```

该脚本把 RPK 推到手机 Download，打开 Mi Fitness 的内部安装页；仍需在手机选择包名、文件并确认安装。它清理该应用的 UI 返回栈，不清除应用数据，不等于安装已成功。此入口依赖当前 mod 内部类，其他版本可能不兼容。

安装后查看 Mi Fitness `handleInstallResult` 的包名、版本号和成功码；再在手表打开「血糖镜像」，核对数值、趋势和测量时间。`发送文件成功` 不足以证明安装成功。

## 容易踩的坑

- APK / RPK 包名与签名必须匹配，见 signing.md。
- Mi Fitness 页面复用旧任务时可能不展示 Debug；辅助脚本使用 NEW_TASK + CLEAR_TASK。
- 部分 Mi Fitness 控件忽略 ADB 零时长 tap；可用同坐标 150 ms swipe 模拟短按。每次先读新 UI 层级，键盘会移动输入框。
- 手机安全锁屏只能由用户解锁，不要关闭锁屏来方便自动化。
- 手表打开时看到旧数值，数秒后变化属于缓存后同步；观察 `sourceAt`，不要只比较数字。
- 不要为了后台刷新声明无关音频或定位权限。
