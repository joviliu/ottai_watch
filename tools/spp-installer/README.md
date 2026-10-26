# 临时 SPP 表盘安装器

仅用于开发验证本项目的 Redmi Watch 6 表盘。它直接使用已配对设备的正常 SPP 认证和表盘上传协议，不调用 Mi Fitness 的云表盘授权接口。不需要解绑或重新配对。本项目 BIN 已在当前设备完成上传，用户确认修正 Lua 入口后正常绘制；配套镜像的两轮自动更新与正常返回已完成基本验收。

## 已签名安装包

可直接使用 [ottai-watchface-installer-0.1.3.apk](../../releases/0.1.8/ottai-watchface-installer-0.1.3.apk)（versionCode 4），先按照 [0.1.8 发布说明](../../releases/0.1.8/README.md)核对 SHA-256。APK 不含配对凭据，也不预装任何健康数据。安装完成后卸载临时安装器，它不参与日常更新。

## 源码构建

加载项目的 Android 工具链环境变量，确保 `.sign/` 已准备好：

```sh
. /absolute/path/to/android.env
python3 tools/spp-installer/build.py --face watchface/build/ottai-minimal-watch6.bin
```

唯一外部依赖为 Bouncy Castle 1.78.1，脚本会校验固定 SHA-256，也可用 `--bc-jar /absolute/path/to/bcprov-jdk18on-1.78.1.jar` 指定已有副本。产物：`tools/spp-installer/build/ottai-watchface-installer.apk`。

构建会运行输入、表盘尺寸/ID和错误脱敏自检；没有模拟无线认证。

## 私密输入

独立包名 `com.example.ottaiwatchfaceinstaller`，debuggable 仅便于开发时通过 `run-as` 放入私有文件。Activity 受系统 `DUMP` 权限保护，只通过 ADB 启动，不提供普通应用可触发的公开安装入口。

- 应用私有 `files/auth.json`：字段 `bluetoothMac`、`authKey`。密钥必须来自当前已配对的自己的设备，不能使用其他项目的默认值。
- 应用私有 `files/watchface.bin`：本项目 BIN；严格要求 ID `8670260101` 与 432×514 预览尺寸。
- 不要把凭据放在此源码目录、APK资源、命令行、终端输出或Git中。

安装 APK 后，Python 示例用 stdin 向应用私有文件写入，凭据不经过命令行或标准输出：

```python
import hashlib, pathlib, subprocess
pkg = 'com.example.ottaiwatchfaceinstaller'
subprocess.run(['adb','shell','run-as',pkg,'mkdir','-p','files'],check=True)
for source, target in [('/absolute/private/auth.json','files/auth.json'),
                       ('/absolute/path/to/ottai-minimal-watch6.bin','files/watchface.bin')]:
    data = pathlib.Path(source).read_bytes()
    # target 仅来自上面的固定列表；不要把凭据或任意用户文本拼进 shell。
    subprocess.run(['adb','shell','-T','run-as',pkg,'sh','-c',"'cat > "+target+"'"],
                   input=data,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True)
    received = subprocess.run(['adb','exec-out','run-as',pkg,'cat',target],
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout
    matched = hashlib.sha256(data).digest() == hashlib.sha256(received).digest()
    print(pathlib.Path(source).name, 'SHA256_MATCH', matched)
    if not matched:
        raise RuntimeError('Private input transfer checksum mismatch')
subprocess.run(['adb','shell','run-as',pkg,'chmod','600','files/auth.json','files/watchface.bin'],check=True)
```

实测本环境中 `adb exec-in ... dd` 曾生成空的认证文件或截断的 BIN，即使命令完成也不能认为传输完整。这里使用 `adb shell -T` 禁用 PTY，再把字节通过 stdin 写给 `cat`；随后必须回读到 Python 内核对 SHA-256。只输出文件名和匹配布尔，不打印认证 JSON、BIN 内容、摘要或密钥。任一文件不匹配时停止，不发起认证或安装。

## 实机操作顺序

1. 先记录「血糖镜像」和 Mi Fitness 的启用状态与已授权通知监听，再暂停它们，避免重新连接占用 SPP；不解绑、不清除应用数据。优先不要改变包的启用状态：本环境 `disable-user` 曾清除两应用原有通知访问，仅重新启用包不会恢复授权。
2. 安装 APK，并授予蓝牙权限：

```sh
adb install -r releases/0.1.8/ottai-watchface-installer-0.1.3.apk
adb shell pm grant com.example.ottaiwatchfaceinstaller android.permission.BLUETOOTH_CONNECT
adb shell pm grant com.example.ottaiwatchfaceinstaller android.permission.BLUETOOTH_SCAN
```

如果自行构建，将安装命令中的 APK 路径替换为 `tools/spp-installer/build/ottai-watchface-installer.apk`。

3. 写入并回读核对上面的两个私有文件。先只认证，确认本轮日志依次出现 `AUTH_OK`、`DISCONNECTED`：

```sh
adb shell am start -S -n com.example.ottaiwatchfaceinstaller/.MainActivity --es mode auth
adb logcat -d -s OttaiFaceInstaller:I
```

4. 仅在上一轮操作已出现 `DISCONNECTED`、Socket 已释放后，再安装本项目表盘；首次安装用 `install`：

```sh
adb shell am start -S -n com.example.ottaiwatchfaceinstaller/.MainActivity --es mode install
```

已有同 ID 的开发版本需更新时，用 `replace`：

```sh
adb shell am start -S -n com.example.ottaiwatchfaceinstaller/.MainActivity --es mode replace
```

`replace` 只能处理固定本项目 ID `8670260101`。安装器先查询表盘列表；若找到该 ID，则只删除此项目表盘，再进行一次独立列表查询，确认该 ID 已不存在后才重装。若查询失败或删除未确认则停止；不会遍历删除其他表盘。没有本项目旧版本时直接安装。保留其他可用表盘作为回退。

本环境中直接再次启动同一个 Activity 曾复用旧 Intent，导致新的 mode 没有执行，因此采用 `am start -S` 启动新实例。`-S` 会先停止已有安装器进程；**上一轮尚未 `DISCONNECTED` 时不可使用**，否则会打断正在进行的认证或传输。判断时看本轮最新日志，不把历史操作的 `DISCONNECTED` 当作当前操作已经结束。

正常完成或错误处理后会关闭 Socket 并记录 `DISCONNECTED`。`INSTALL_OK` 表示上传流程和激活请求发送完成；当前实现没有单独核对激活响应，因此仍需设备列表或目视确认实际安装、渲染与数据动态更新。

5. 结束后确认 `DISCONNECTED`，释放安装器，再按下面的恢复检查还原日常同步。随后卸载此临时安装器以删除其私有凭据；它不参与日常血糖同步：

```sh
adb uninstall com.example.ottaiwatchfaceinstaller
```

## 安装后的恢复检查

- 恢复 Mi Fitness 与镜像原先的启用/运行状态。本轮恢复为 `default`；新环境依照开始前记录，不擅自改变用户原设置。
- 若曾用 `disable-user`，核对系统“通知使用权/通知访问”：恢复此前已授权的镜像 `OttaiMetadataListener` 和 Mi Fitness `NotifySyncService`，不额外授权其他监听服务。它们的通知访问可能已被系统清除，不能仅检查蓝牙连接。
- 启动并重连 Mi Fitness 与镜像。镜像手机 `MainActivity` 会发起 `NotificationListenerService.requestRebind`，用于恢复已获授权的监听绑定，不能代替被撤销的通知授权。
- 对照最新 Ottai 通知核对镜像接收的原始测量时间、数值和趋势，再观察表盘；停留在旧缓存或仅看到连接成功不算恢复完成。不要公开原始通知、医疗时间线或设备标识。
- 如需“表盘自动同步”，在手机明确开启。保持手表在表盘、不手动打开镜像，检查后续至少两个自然更新周期；文件导出回执和 ACK 不能代替表盘目视确认。

## 当前验证状态

| 阶段 | 状态 |
| --- | --- |
| 本地正常 SPP 认证 | 已在当前设备收到 `AUTH_OK` 并完成 `DISCONNECTED` |
| 本项目 BIN 安装 | `replace` 已收到 `UPLOAD 100%`、`INSTALL_OK`，并完成 `DISCONNECTED` |
| 表盘渲染 | 修正打包器 Lua anchor 入口后，用户确认正常绘制 |
| 安装器清理 | 已卸载成功；手机保持锁屏，镜像与 Mi Fitness 原通知访问保留 |
| 自动同步 | 用户确认自动返回点阵表盘并显示当前读数；手机锁屏后连续两轮自然更新完成导出及 ACK，用户已确认最新屏显与正常返回，基本验收通过。此能力来自镜像应用的短暂唤起策略，非安装器或常驻后台 |

此组件源码独立采用 AGPL-3.0，协议来源及依赖见 NOTICE.md。没有联网权限、广泛存储权限或固件更新功能。
