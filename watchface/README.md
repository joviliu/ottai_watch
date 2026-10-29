# Redmi Watch 6：三款 Lua 血糖表盘

2026-10-29：0.1.14 三款已通过本地 SPP 安装并由用户逐款确认可见。最新 [0.1.15](../releases/0.1.15/README.md) 优化 Signal 电子数字、Meridian 全宽圆盘，并让两款接入同一 32 组分时配色；覆盖/最终验收进行中，实时状态以 [交接记录](../docs/HANDOFF.md) 为准。当前客户端已按用户要求切回修改版 3.33.6i 作安装对照；官方日常同步的历史结果保留。

| 款式 | 固定 ID | 设计 |
| --- | --- | --- |
| Ottai Ultra | `8670260101` | 保留已确认的点阵布局；04/11/15/19 换组，32 组柔和双色；日期与更新时间同灰 |
| Ottai Signal | `8670260102` | 原创七段电子数字、独立血糖卡片与指标行；32 组分时配色 |
| Ottai Meridian | `8670260103` | 408 像素圆盘、盘面血糖浮层、32 组分时指针配色；无秒针，指针每分钟更新 |

三款都有时间、日期、血糖、趋势、原始更新时间、电量和心率，独立 ID 可并存。沿用同一 RPK 与同一合法数据文件，无需新增手机采集应用。保留原始测量时间与 OLD；没有新增通信、传感器轮询或常驻后台。

布局默认值在 [layout.json](layout.json)，新款覆盖参数在 [faces.json](faces.json)；打包与 Lua 共用生成的 layout.lua。配色及来源见 [说明](../docs/clock-palettes.md)。Ultra 原时钟 6×14、90×232、位置不变，血糖仍为稀疏 5×7；新款使用实心数字，Meridian 指针预渲染为透明图片，复用既有 Image API，不依赖未验证的图形旋转接口。

日期与血糖更新时间均为 `#B9C2C8`；旧数据仍保留 OLD 及血糖色系变暗。选择器缩略图的血糖/时间/指标为占位，正常运行只取真实文件，合成示例不写入设备。

## 用户自定义显示颜色

按表盘的一位小数有效显示值 `v` 分段，数值和趋势箭头使用相同颜色：

| 显示值范围 | 新鲜读数颜色 |
| --- | --- |
| `3.9 <= v <= 7.8` | 紫色 `#924ff7` |
| `7.8 < v <= 12.0` | 黄色 `#ffd60a` |
| 其余有效值 | 红色 `#ff453a` |

边界 `7.8` 为紫色、`12.0` 为黄色；小于 `3.9` 或大于 `12.0` 为红色。旧数据仍显示原始时间与 `OLD`，数值和箭头在各自色系中变暗，不把旧读数改成新鲜读数。这是用户自定义的显示分段；不改变数据、提醒或告警逻辑。配色升级当时保持手机 APK 0.1.10 和 RPK 0.1.8 不变；当前手机 0.1.11 的后台修复仍沿用相同表盘配色与协议。动态配色版已通过 SPP 覆盖当前 ID `8670260101`，恢复默认启用状态及原通知监听后卸载临时安装器。三色、边界及过期分支已完成桌面测试；此前用户目视确认的是相同布局的静态紫色版，本次未额外确认真实数据下的颜色分段切换。

[配色预览](preview-colors.png)使用合成示例，供比较三种颜色及旧数据样式，不是实机血糖截图。

## 构建与测试

在仓库根目录运行：

```sh
python3 -m venv .toolchain/watchface-venv
.toolchain/watchface-venv/bin/pip install -r watchface/requirements.txt
.toolchain/watchface-venv/bin/python watchface/test_frame.py
.toolchain/watchface-venv/bin/python watchface/test_ui.py
.toolchain/watchface-venv/bin/python watchface/build.py --variant all
.toolchain/watchface-venv/bin/python watchface/test_assets.py
```

另需 Node.js 测试真实 JS 导出兼容性。构建使用 Pillow；Ultra 时钟/血糖来自原创点阵；新款时间/血糖使用原创七段电子图案，Barlow Condensed SemiBold 仅用于刻度文字和静态预览标识，Barlow Light 用于预览及 unknown 问号，Lupa 仅用于桌面 Lua 测试。不依赖 Windows、EasyFace 或官方编译器。

输出位于忽略的 `watchface/build/`：

- `ottai-minimal-watch6.bin`：Ottai Ultra Lua 容器，ID `8670260101`。
- `ottai-minimal-watch6.zip`：Mi Fitness 内部开发入口封装，不是商店发布包。
- `preview-example.png`：合成布局预览，不是实机截图。
- `manifest.json`：ID、尺寸、体积和 SHA-256；另含生成素材及 `layout.lua`。
- `signal/ottai-signal-watch6.bin/.zip`、`meridian/ottai-meridian-watch6.bin/.zip`：另外两款，各有预览和 manifest。

选择器的血糖/时间使用 `--` 与 `--:--` 占位，设备只显示合法文件读数，不把合成预览当实时数据。

## 数据更新

Vela 应用接收合法帧后，通过 `system.file` 写入双槽文件；Lua 表盘只读这些文件。格式和校验规则见 [数据协议](../docs/protocol.md)。发现更旧、损坏或未写完整的文件时保留最后合法读数及其测量时间。

表盘创建、亮屏和页面恢复时检查文件；亮屏且可见期间每 15 秒检查小文件，息屏或离开表盘后暂停该计时器。不轮询传感器，不用静音音频或定位保活。电量与心率通过 `dataman` 订阅，缺少有效值时显示占位。

**文件读取不等于后台更新已打通。** 实测表端应用隐藏后的两轮被动发送没有对应 ACK 或文件回执。现有策略先发送，8 秒未取得完整身份的文件确认才短暂唤起同步页，写入成功后退出；手机“表盘自动同步”新安装默认关闭。历史 0.1.8 两轮短锁屏约 9.8/9.7 秒并有用户屏显确认，只能证明这两轮连通与返回，未先确认 Home 后的后台状态。本轮 0.1.10 第一次由用户打开手表应用才导出，只有第二次自动完成，不能记两轮自动通过。

手机 0.1.11 的新读数/发送尝试有每次至多 20 秒 CPU 窗口，当前完整身份导出即提前释放；60 秒唤起冷却只限制相同身份，新测量或同时间更正不被旧身份挡住。它不改变文件格式，也不能解冻厂商冻结。此前手机 0.1.11 + RPK 0.1.8 已完成恢复补传及三个镜像持续后台的正常自然周期文件导出；前两轮屏显和自动返回已由用户确认，实际省电设置、验收标准及边界见 [后台排查](../docs/background-running.md)。它仍是必要时自动短暂打开应用后返回的策略；其他页面影响、断连恢复、长期稳定性、AOD 和耗电尚未完整验收。真实趋势目前只验证到水平箭头，斜向等方向仅完成映射测试。

0.1.8 的导出回执以 `sourceAt|规范数值|原始趋势` 的完整 `frameKey` 匹配当前读数，区分同时间的数值/趋势更正。文件发布串行执行，只保留最新待发布帧；旧完成不会越过新帧确认或触发退出，已写同身份可复用确认。自动同步会话绑定完整身份，设备延迟启动时仍保留返回标志。新合法帧先取消旧退出定时器，最新写入完成后重新安排，退出前再次核对当前身份；离页清理返回意图。

[RPK 0.1.9 试验](../releases/watch-0.1.9/README.md) 未通过验收、不推荐使用：手动启动先黑屏，透明未透出表盘；两轮自动周期手机有新帧、唤起和 SDK accepted，但没有文件导出回执，用户未见数据更新。镜像未冻结，具体失败原因尚未定位。源码已恢复原 0.1.8 逻辑，仅将版本递增为 [RPK 0.1.10 / code 11](../releases/watch-0.1.10/README.md) 供覆盖安装；已确认安装 code 0，两次旧测量自动写入已确认，恢复旧测量时的表盘原始时间和正常返回已由用户确认；随后两个原始时间推进的读数均已自动导出并收到 ACK，本两条未额外取得屏显目视；上述三周期证据只属于原 RPK 0.1.8。手机和表盘无需重装，试验差异见 [implementation.patch](../experiments/watch-transparent-0.1.9/implementation.patch)，后续边界见 [减少界面闪现调研](../docs/silent-sync-research.md)。

## 安装入口与验收

手机 APK 仍用 [0.1.11](../releases/0.1.11/README.md)，表盘候选见 [0.1.15](../releases/0.1.15/README.md)，新增基准线的 RPK 为 [watch-0.1.12](../releases/watch-0.1.12/README.md)。临时安装器沿用 0.1.5/code6；最终安装、清理和后台验收以 [交接记录](../docs/HANDOFF.md) 为准。各目录先核对 SHA256SUMS，升级须保留原包名/签名，不要求 APK 与 RPK 版本号一致。

先完成 [安装文档](../docs/install.md) 的工具链与签名配置，然后可打开开发入口：

```sh
. .toolchain/android.env
python3 tools/open_installer.py --serial SERIAL --watchface watchface/build/ottai-minimal-watch6.zip
```

Mi Fitness 开发入口在授权接口 HTTP 404 处失败；打开页面、解压成功或请求授权均不表示安装完成。[本地 SPP 临时安装器](../tools/spp-installer/README.md) 已完成正常认证、100% 上传及断开，用户也已确认修正 Lua 入口后的表盘正常绘制。历史用安装器 0.1.4 的 `replace` 覆盖 `8670260101`。本轮构建安装器 0.1.5，白名单仅包含上表三款：Ultra 用 replace，另外两款首次用 install；只操作当前 BIN 目标，保留其他 ID。只能使用用户自己设备的合法配对密钥，密钥不得进入仓库或日志输出。

曾出现“上传完成但黑屏”：容器中上游命名为 `sentinel` 的字段实际是 Lua anchor payload 的资源索引，默认 `n-1` 在本项目指向趋势 PNG，而 `lua/main.lua` 当时位于索引 14。构建现在按文件名确定 `main_index`，打包后解包断言确实指向 `lua/main.lua`，不能把 14 当作以后固定入口。

暂停蓝牙桥接后须恢复 Mi Fitness 与镜像的原运行状态及原有通知授权；尤其 `disable-user` 可能清除通知访问。恢复及正常重启后必须实际核对默认启用状态、原通知授权及监听绑定，不能仅信 `pm` 输出；再确认最新自然 Ottai 通知进入镜像，不能用恢复旧缓存通知的回执作为新周期验收。

新环境基本验收应复验：安装成功且其他表盘可回退；字体和数值目视正常；手机先 Home 确认为 FGS 后台，再锁屏，至少两个 Ottai 自然周期不手动打开两端镜像，核对通知未积压、自动唤起、完整身份文件确认、测量时间推进及表盘正常返回。当前设备的布局与通知图标已有确认，历史短锁屏通过不替代这项严格验证；此前手机 0.1.11 + RPK 0.1.8 已完成恢复补传及三个镜像持续后台的正常自然周期文件导出；前两轮屏显和自动返回已由用户确认。新环境也应复验大时钟、配色、稀疏血糖居中和左时间/右箭头。旧数据标记、断连与休眠恢复、长按换表盘及其他页面行为仍需继续验证；当前没有单独 AOD 子工程，息屏显示、长期稳定性及耗电尚未完整验收。

## 来源

`vendor/facebin.py` 来自 [AIR-pixel/miband11-watchface-maker](https://github.com/AIR-pixel/miband11-watchface-maker)，commit `3af1bb2292cdf5298830a8fcaac817ae631ab003`，MIT。这里将预览改为 432×514，解包时读取头部索引指针，修正预览头的解析格式，并说明 Lua anchor 必须指向主脚本；构建显式按文件名选择入口。许可证在 `vendor/LICENSE.facebin`。

时钟使用原创 6×14 点阵，血糖使用原创稀疏 5×7 点阵，不依赖字体轮廓。[Barlow Condensed Light](https://github.com/google/fonts/tree/main/ofl/barlowcondensed)仅用于桌面预览文字和 unknown 趋势问号，SIL OFL 1.1，许可证在 `fonts/OFL.txt`。Lua 使用设备自带 MiSans 绘制其他文本，不分发原厂表盘素材。更多来源见 [第三方声明](../THIRD_PARTY_NOTICES.txt)。

后续不同风格可采用独立表盘 ID 实现并存，继续共用现有镜像 RPK 和数据文件；相同 ID 会覆盖已有样式。当前已有三个独立 ID；同 ID 的新布局以覆盖方式更新，其他款保留。

## 字体来源

[Barlow Condensed](https://github.com/google/fonts/tree/main/ofl/barlowcondensed) 按 [SIL OFL](fonts/OFL.txt) 使用；SemiBold 原文件 SHA-256 为 `7b619d14bc2327509a9ef32b0890f709626f7ecc9ff61191c2a4314c5499d2d9`。新数字在构建时转为 PNG，设备无需另外安装字体。
