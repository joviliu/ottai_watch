# 0.1.8：血糖应用与点阵表盘

先在本目录运行 `shasum -a 256 -c SHA256SUMS`（Linux 可用 `sha256sum -c SHA256SUMS`）。

| 文件 | 用途 |
| --- | --- |
| `glucose-watch6-0.1.8.apk` | 手机通知桥接，versionCode 9；与既有本项目安装包同签名 |
| `glucose-watch6-0.1.8.rpk` | Redmi Watch 6「血糖镜像」，versionCode 9，写入表盘数据文件 |
| `ottai-minimal-watch6.bin` | 原创 432×514 白色圆点时钟、橙色血糖/趋势表盘，固定 ID `8670260101` |
| `ottai-minimal-watch6.zip` | 同一表盘的 Mi Fitness 开发入口封装；本次该入口授权 HTTP 404，实际安装使用上面的 BIN |
| `ottai-watchface-installer-0.1.3.apk` | 独立临时 SPP 安装器，versionCode 4；上传 BIN 后卸载，日常同步不依赖它 |

手机/手表包均为 `com.example.glucosewatch6`。手机开启通知访问、蓝牙通道与「表盘自动同步」；此开关新安装默认关闭。自动同步在后台发送未确认后短暂唤起手表应用，写入后自行返回，不是常驻后台服务。

当前设备已通过正常绘制、自动返回及手机锁屏后的两轮自然更新验证，见 [验证记录](../../docs/validation.md)。兼容性仅覆盖记录中的设备/固件组合；长期耗电尚未测量。

安装器包名为 `com.example.ottaiwatchfaceinstaller`，仅供 ADB 开发使用，不含配对凭据。需要自己设备的合法配对凭据，并按 [安装器说明](../../tools/spp-installer/README.md) 操作；`replace` 只替换上述固定表盘 ID，不删除其他表盘。安装完成后卸载临时安装器。

完整安装步骤见 [安装与排查](../../docs/install.md)，继续开发见 [HANDOFF](../../docs/HANDOFF.md)。主项目 GPL-3.0、独立安装器 AGPL-3.0，源码与第三方许可证均在仓库；不含第三方 APK、原厂表盘素材或运行时健康数据。
