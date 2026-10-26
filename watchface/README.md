# Ottai Minimal：Redmi Watch 6 Lua 表盘

这是原创 432×514 表盘工程，采用紧凑日期、约占屏幕上方三分之二的细长大时钟，以及下方的血糖数值、趋势箭头、原始测量时间、电量和心率。血糖不显示单位，不画曲线。时钟为白色完整圆点，冒号、血糖和趋势箭头为橙色；旧读数减弱颜色并显示 `OLD`，原始时间仍保留。数字 PNG 和 Image 控件均为 88×234，不在设备上缩放圆点。

**开发版基本验收通过。** 本地 SPP 已完成上传，修正 Lua 入口后表盘正常绘制；手机锁屏、不手动打开镜像的连续两轮自然更新均收到文件导出和 ACK。用户确认最新数值、水平趋势与原始时间显示正确，自动返回正常，未报告明显闪屏或卡住；十几秒的观察延迟可接受。Mi Fitness 开发安装页的 `designer_license` 授权接口仍返回 HTTP 404，本地 SPP 是此次实际采用的安装路径。参见 [当前验证状态](../docs/validation.md) 和 [接续任务](../docs/HANDOFF.md)。

## 构建与测试

在仓库根目录运行：

```sh
python3 -m venv .toolchain/watchface-venv
.toolchain/watchface-venv/bin/pip install -r watchface/requirements.txt
.toolchain/watchface-venv/bin/python watchface/test_frame.py
.toolchain/watchface-venv/bin/python watchface/test_ui.py
.toolchain/watchface-venv/bin/python watchface/build.py
```

还需要 Node.js，用于测试真实 JS 导出与 Lua 读取的兼容性。构建使用 Pillow 和仓库内字体，不依赖 Windows、EasyFace 或官方编译器。Lupa 只用于桌面 Lua 测试。

输出在忽略的 `watchface/build/` 中：

- `ottai-minimal-watch6.bin`：Lua 表盘容器，使用本项目独立 ID。
- `ottai-minimal-watch6.zip`：Mi Fitness 内部开发安装入口需要的目录封装；内含 `resource.bin`、资源目录标记、预览和映射文件。这个 ZIP 不是表盘商店发布包。
- `preview-example.png`：包含合成示例的布局预览，不是手表截图。时钟数字素材与表盘相同；预览中的文本字体不能证明设备原生字体的实际效果。
- `manifest.json`：屏幕尺寸、文件数量、体积和 SHA-256。

安装选择器中的血糖区域使用 `-- / WAITING` 占位，运行时只有读取到有效文件才显示血糖，不把合成示例当成实时读数。

## 数据更新

Vela 应用接收合法帧后，通过 `system.file` 写入双槽文件；Lua 表盘只读这些文件。格式和校验规则见 [数据协议](../docs/protocol.md)。发现更旧、损坏或未写完整的文件时保留最后合法读数及其测量时间。

表盘创建、亮屏和页面恢复时检查文件；亮屏且可见期间每 15 秒检查小文件，息屏或离开表盘后暂停该计时器。不轮询传感器，不用静音音频或定位保活。电量与心率通过 `dataman` 订阅，缺少有效值时显示占位。

**文件读取不等于后台更新已打通。** 实测镜像应用隐藏后，连续两轮手机新通知没有对应的表端 ACK 或文件写入回执。0.1.8 方案先尝试后台发送，8 秒未确认时才短暂唤起同步页；写入成功后自动退出。它无需用户手动打开，但实质仍是短暂唤起应用，不是常驻后台服务。手机“表盘自动同步”开关新安装默认关闭；当前设备已开启，并已观察到一次后台发送未确认后自动唤起、文件导出和 ACK。用户已确认自动返回和读数显示，手机锁屏后连续两轮自然更新的源测量时间相隔 5 分钟且数值变化，通知接收到 ACK 分别约 9.8 秒和 9.7 秒；这不是表盘显示延迟。用户已确认最新一轮屏显与正常返回，未报告明显闪屏或卡住；对其他页面的影响、断连恢复、长期稳定性、AOD 和耗电尚未完整验收。真实趋势目前只验证到水平箭头，斜向等方向仅完成映射测试。

0.1.8 的导出回执以 `sourceAt|规范数值|原始趋势` 的完整 `frameKey` 匹配当前读数，区分同时间的数值/趋势更正。文件发布串行执行，只保留最新待发布帧；旧完成不会越过新帧确认或触发退出，已写同身份可复用确认。自动同步会话绑定完整身份，设备延迟启动时仍保留返回标志。新合法帧先取消旧退出定时器，最新写入完成后重新安排，退出前再次核对当前身份；离页清理返回意图。

## 安装入口与验收

可直接使用 [0.1.8 发布目录](../releases/0.1.8/README.md)的匹配 APK/RPK、表盘 BIN 和临时安装器，先核对校验和。此次验证后临时安装器已卸载；日常同步只需要原有镜像和 Mi Fitness 通道。

先完成 [安装文档](../docs/install.md) 的工具链与签名配置，然后可打开开发入口：

```sh
. .toolchain/android.env
python3 tools/open_installer.py --serial SERIAL --watchface watchface/build/ottai-minimal-watch6.zip
```

Mi Fitness 开发入口在授权接口 HTTP 404 处失败；打开页面、解压成功或请求授权均不表示安装完成。[本地 SPP 临时安装器](../tools/spp-installer/README.md) 已完成正常认证、100% 上传及断开，用户也已确认修正 Lua 入口后的表盘正常绘制。升级本项目表盘可用 `replace`：仅删除固定本项目 ID，并独立查询确认删除后再安装；不删除其他表盘，不解绑。只能使用用户自己设备的合法配对密钥，密钥不得进入仓库或日志输出。

曾出现“上传完成但黑屏”：容器中上游命名为 `sentinel` 的字段实际是 Lua anchor payload 的资源索引，默认 `n-1` 在本项目指向趋势 PNG，而 `lua/main.lua` 当时位于索引 14。构建现在按文件名确定 `main_index`，打包后解包断言确实指向 `lua/main.lua`，不能把 14 当作以后固定入口。

暂停蓝牙桥接后须恢复 Mi Fitness 与镜像的原运行状态及原有通知授权；尤其 `disable-user` 可能清除通知访问。恢复后核对镜像已收到最新 Ottai 通知，再观察动态更新，不能沿用旧缓存作为验收。

新环境基本验收应复验：安装成功且其他表盘可回退；字体和数值目视正常；不手动打开镜像应用的情况下，至少两个 Ottai 更新周期的测量时间推进，数值和趋势与手机一致，并正常返回表盘。当前设备的这部分基本验收已通过。旧数据标记、断连与休眠恢复、长按换表盘、其他页面受自动唤起影响的行为仍需继续验证。当前没有单独 AOD 子工程，息屏显示、长期稳定性及耗电尚未完整验收。

## 来源

`vendor/facebin.py` 来自 [AIR-pixel/miband11-watchface-maker](https://github.com/AIR-pixel/miband11-watchface-maker)，commit `3af1bb2292cdf5298830a8fcaac817ae631ab003`，MIT。这里将预览改为 432×514，解包时读取头部索引指针，修正预览头的解析格式，并说明 Lua anchor 必须指向主脚本；构建显式按文件名选择入口。许可证在 `vendor/LICENSE.facebin`。

时钟以 [Barlow Condensed Light](https://github.com/google/fonts/tree/main/ofl/barlowcondensed)为轮廓生成原创圆点 PNG，SIL OFL 1.1，许可证在 `fonts/OFL.txt`。Lua 使用设备自带 MiSans 绘制其他文本，不分发原厂表盘素材。更多来源见 [第三方声明](../THIRD_PARTY_NOTICES.txt)。
