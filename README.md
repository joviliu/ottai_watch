# Ottai → Redmi Watch 6 血糖镜像

把手机欧态 Ottai 通知中的血糖、趋势、原始测量时间，经小米运动健康的蓝牙通道发送到 Redmi Watch 6。当前可用的是独立手表应用「血糖镜像」，含数值、趋势、更新时间和最近曲线。无需 xDrip。

## 当前状态

| 项目 | 状态 |
| --- | --- |
| Android 通知监听与蓝牙桥接 | 0.1.4，已实机运行 |
| Vela 手表应用 | 0.1.4 基线已实机显示数值、趋势和曲线；0.1.5 大圆图标已安装并由用户确认 |
| 更新策略 | Ottai 新通知触发；进入手表应用/通道重连时请求最新数据 |
| 缓存 | 进入时保留上次数值和测量时间，随后同步；断连不把旧数据伪装成新数据 |
| 上滑「小部件」 | 尚未找到可确认用于 Watch 6 第三方应用的公开接口 |
| 自定义血糖表盘 | 调研中，见 [快捷查看调研](docs/quick-view-research.md) |

当前实机组合：Xiaomi 15 / Android 16；Redmi Watch 6（M2523W1，固件 3.100.043，432×514）；Ottai `com.ottai.tag` 1.63.0；Mi Fitness mod `com.xiaomi.wearable` 3.33.6i m0tral v141。兼容性结论仅覆盖这套组合。

Ottai 约每 5 分钟更新一次。程序不轮询传感器、不提高 Ottai 刷新频率，也不在每次读数到达时弹开手表应用。前台每分钟只重算数据年龄；应用隐藏后停止该计时器。

## 新环境快速开始

```sh
git clone git@github.com:joviliu/ottai_watch.git
cd ottai_watch
```

**直接安装**：使用 [releases/0.1.4](releases/0.1.4) 内同签名的 APK + RPK，先核对 `SHA256SUMS`；参照 [安装与排查](docs/install.md)。安装包不包含运行时健康数据和账号。

较新手表图标包在 [releases/0.1.5](releases/0.1.5)，搭配手机 0.1.4 使用，数据协议与签名一致。

**继续开发**：需要 Python 3、Node.js ≥18、JDK ≥17、Android SDK Platform 35 / Build Tools 35.0.0、OpenSSL。先运行不依赖 Android SDK 的测试：

```sh
export JDK=/absolute/path/to/jdk
sh tools/test.sh
```

首次构建：

```sh
# 先阅读 docs/signing.md：升级已安装的版本必须迁移原签名私钥。
sh tools/prepare_signing.sh
python3 tools/setup_android.py --sdk /absolute/path/to/android-sdk --jdk "$JDK"
. .toolchain/android.env
python3 tools/build_android.py
cd watch
npm ci
npm test
npm run release
```

Android 产物在 `android/build/`；手表产物在 `watch/dist/`。如已有工具链，也可按 `tools/build.env.example` 手动设置环境变量。

## 项目结构

- `android/src/`：通知解析、缓存、前台蓝牙服务、手机界面及图标。
- `android/vendor/sdk/`：小米 Wearable SDK 源码，来源和修改见 `THIRD_PARTY_NOTICES.txt`。
- `watch/src/`：Vela JS 应用。`common/model.js` 负责消息和曲线校验；`pages/index/index.ux` 负责连接、缓存、展示和回执。
- `android/test/`、`watch/test/`：通知时间、非法帧、曲线中断、缓存保留、Object 消息、ACK 和非轮询策略测试。
- `tools/`：构建、签名、安装入口辅助脚本。
- `docs/`：协议、安装、签名、接续任务与快捷查看调研。
- `releases/`：本项目自己的签名安装包和校验和。

## 接续任务

先读 [HANDOFF](docs/HANDOFF.md)，再看 [数据协议](docs/protocol.md) 与 [快捷查看调研](docs/quick-view-research.md)。不要把「SDK 发送成功」当作「手表已显示」；手机界面分别显示发送状态、当前帧首次回执和最近回执。

本公开仓库不存放签名私钥、蓝牙配对密钥、账号、真实血糖日志、第三方 APK 或原厂表盘素材。签名迁移见 [签名说明](docs/signing.md)。代码采用 GPL-3.0，包含的第三方代码说明见 [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.txt)。
