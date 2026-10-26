# Watch 6 小部件、手势与血糖表盘调研

调研日期：2026-10-26。实机固件 3.100.043。结论中的「未找到」表示公开资料与当前代码核查的边界，不等于硬件永远不支持。

## 结论

1. **上滑小部件是系统功能，但当前未找到可确认接入的第三方注册/数据提供接口。** 不把本应用普通页面声明成一个「小部件」后就声称已经支持。
2. **自定义表盘已安装并正常绘制。** 原创 Lua UI、文件校验读取和 macOS 纯代码构建已完成；Mi Fitness 开发授权仍为 HTTP 404，实际采用独立 SPP 安装。0.1.10 单款 Ottai Ultra 的布局和正常重启后的通知图标已确认；0.1.8 两轮短锁屏更新仅为历史连通性基线。后续发现 HyperOS Greezer 会冻结仍有常驻通知的手机进程，当前手机 0.1.11 已安装，已完成恢复补传及两个镜像持续后台的自然周期文件导出；后一轮屏显待用户确认，不能沿用历史短锁屏结果声称后台问题已解决。
3. 当前可立即采用的官方选项是调整「设置 → 桌面表盘 → 返回表盘」时间，使打开血糖应用后更容易再次查看。这不会把它变成系统卡片，也不能据此保证后台持续更新。

## 上滑小部件

小米 [Watch 6 官方 FAQ，Q10](https://www.mi.com/uk/support/faq/details/KA-694585/) 确认：表盘上滑进入小部件，长按进入编辑，底部加号添加。文档没有说明用户如何将第三方 RPK 注册到这个列表。用户实机已经查看，列表中没有「血糖镜像」。

[Vela 官方 manifest 文档](https://iot.mi.com/vela/quickapp/zh/guide/framework/manifest.html) 的公开路由为 `router.entry`、`router.pages`，没有描述 Watch 6 系统卡片注册、数据 provider 或更新生命周期。

额外核查了锁定的 `aiot-toolkit@2.0.5` / `@aiot-toolkit/aiotpack`：

- `lib/compiler/javascript/vela/interface/IManifest.d.ts` 确有 `router.widgets` 和 `IWidget`：`name`、`component`、`minCardPlatformVersion`、`providerUri`、`sizes`、`type`。
- `lib/utils/BeforeCompileUtils.js` 会收集 `type: lite` 的路由。
- `lib/compiler/javascript/vela/utils/LiteCard.js` 调用 `hap-toolkit.compile('native', ...)`。
- `lib/afterCompile/ux/UxAfterCompile.js` 的 `compileLiteCard` 复制 `.template.json` 和 `.css.json`，没有同时复制卡片 JS。

**推断**：工具包包含通用快应用轻卡编译代码；它尚不能证明此固件提供对应宿主和 provider。参考 [hapjs 官方工具链](https://github.com/hapjs-platform/hap-toolkit) 中的同类 `minCardPlatformVersion` 实现也不能直接套用到手表。下一步若测试 manifest，应使用独立实验包，在真机确认是否出现在「+」列表并实际更新，避免改动正在工作的主包。

## 左右滑、双击与按键

没有找到官方资料支持将原厂表盘的全局左右滑、双击任意绑定到第三方 RPK。Lua 表盘内部处理点击/手势是另一层能力，不能改变原厂表盘或系统的全局行为。

官方 FAQ Q26 记录了「返回表盘」时间设置，可作为现有独立应用的临时便利设置。仍需用户在当前国行固件确认具体可选时长；没有自动改动用户设置。

## 可参考的真实表盘工程

| 参考 | 核查结果 | 对本项目的意义 |
| --- | --- | --- |
| [maga32/RedmiWatch6-watchface-calendar](https://github.com/maga32/RedmiWatch6-watchface-calendar) | 提供 `calendarWatch.fprj`、`app/lua/main.lua` 和 1.1 `.bin` 发布包；工程 `DeviceType=465`，432×514，Shape 34 加载 Lua | 直接针对 Watch 6 的 UI/打包参考；不复制其未声明授权的素材和代码 |
| [m0tral/MiWatchLuaWatchfaces](https://github.com/m0tral/MiWatchLuaWatchfaces) | Lua/LVGL、`dataman` 时间订阅、MiSans 字体、`io.open` 等实例；主要是其他设备 | 参考运行方式；不能把其他型号上的路径/生命周期视为 Watch 6 已验证 |
| [m0tral/EasyFace](https://github.com/m0tral/EasyFace) | 作者当前 README 明确列出 Redmi Watch 6；其工具链为 Windows MSI + VC++ x86 运行库 + 编译器更新 | 可作为参考；本项目现已采用下述纯代码构建，不依赖该 Windows 环境 |
| [miguelavh/Watchdrip-Xiaomi](https://github.com/miguelavh/Watchdrip-Xiaomi) | README 主要覆盖 Band 8 Pro/9/10 与 Watch 4 | 不能作为 Watch 6 无需适配的证明 |
| [Watchdrip 作者说明](https://bigdigital.home.blog/2024/11/28/xiaomi-89-support/) | 既有桥接应用 + 专用表盘路线 | 可继续寻找作者表盘的数据读取实现，而非只照搬旧尺寸表盘 |
| [calinhoria/watchface-installer](https://github.com/calinhoria/watchface-installer) | 有 Watch 6 SPP 安装协议和预览解析的源码；AGPL-3.0 | 本次已用于最终 `.bin` 的 SPP 安装，不单独解决动态数据；不使用其内嵌默认配对密钥或 APK |

核查的版本：`maga32` commit `6e8a21ebbe9740ba233eec3a859b657e41e595fd`；`MiWatchLuaWatchfaces` commit `5af6e14ea92830a394c88dc04f76ceef697a6ded`。

## 本轮开发发现与剩余缺口

已找到 [WatchDrip 作者的 Lua 表盘源码](https://github.com/miguelavh/LUA_Watchdrip_Watchface_graph_Xiaomi_band9/blob/59297c999c3f5591c6a9c6d095d7e80c883990f2/app/lua/main.lua)，其中从 `/data/quickapp/files/<package>/info.json` 读取快应用导出数据。这补上了读取端的参考，但不证明 Watch 6 当前固件的映射和权限。开源 [Vela 路径实现](https://github.com/open-vela/frameworks_runtimes_feature/blob/e20440fe7d970609bd3f02e9335b1a85e4fcb148/modules/app_path.cpp) 也说明 URI 映射是运行时细节，不能把一个型号上的路径视为跨固件保证。

本项目现在保留 `system.storage` 作为应用缓存，另通过 `system.file` 导出带校验的双槽记录；Lua 只尝试本包目录中的三个候选映射。格式见 [protocol.md](protocol.md)。打开镜像应用时已经收到文件 API 写入成功回执；现在表盘已安装并正常绘制，用户已确认表盘显示导出读数及原始时间，后续仍须以自然更新时的测量时间、数值和趋势核对动态链路，不能用单一写入回执替代。

被动后台实验已观察两个真实通知周期：手机收到并发送新帧，隐藏的表端应用没有对应 ACK 或文件导出回执。由此不能把文件存在或 SDK success 当成持续更新保证。原 WatchDrip Android 方案本身也使用先启动表端应用再发送的路线，不能据其文件读取代码推断应用常驻后台。

0.1.8 备用方式先正常发送，8 秒未确认才短暂唤起同步页；写入成功后自动返回，手机开关新安装默认关闭。完整读数身份与串行发布避免同时间更正被旧确认覆盖。历史两轮短锁屏通知到 ACK 约 9.8/9.7 秒，且有用户屏显与返回确认；当时没有确认 Home 后的后台状态，不证明长期可靠更新。本轮 0.1.10 两次复核中，第一次由用户手动打开才导出，只有第二次自动完成，不能计作两轮自动通过。手机 0.1.11 补上至多 20 秒的单次 CPU 执行窗口与仅同完整身份的唤起冷却；RPK 0.1.8、表盘 0.1.10 不变。本轮已完成恢复补传及两个镜像持续后台的自然周期文件导出；后一轮屏显待用户确认，详见 [后台排查](background-running.md)。斜向趋势尚只有映射测试，对其他手表页面的影响、断连恢复、长期稳定性、AOD 与耗电仍需继续验收。

## 构建与安装路线

新增参考 [AIR-pixel/miband11-watchface-maker](https://github.com/AIR-pixel/miband11-watchface-maker)，commit `3af1bb2292cdf5298830a8fcaac817ae631ab003`，提供 MIT 许可的纯代码 `.face` 格式实现。本项目适配 432×514 预览和解包头部后可直接在 macOS 构建 BIN 与开发安装 ZIP，打包往返和 Lua 桌面测试已通过。不能把原项目其他设备的实测结论迁移为 Watch 6 已验证。

Mi Fitness `FaceDesignerFragment` 能解压本项目 ZIP，但当前 mod 的强制签名授权 `designer_license` 请求仍为 HTTP 404。本次独立 SPP 安装器使用本机合法配对密钥，已完成认证、100% 上传和断开，用户确认修正入口后正常绘制；未解除配对，也不使用任何参考项目默认密钥。

实测黑屏原因是打包器所谓 `sentinel` 字段实际为 Lua anchor 资源索引，默认 `n-1` 在本工程指向趋势 PNG。构建现按文件名确定 `lua/main.lua` 并往返断言；这与授权服务、字体或血糖通知无关。临时暂停应用后的恢复还需核对原有通知访问及最新 Ottai 到达，不能只恢复蓝牙。

## 当前布局

最初的 [布局 SVG](../watchface/minimal-layout.svg) 保留作为历史草图。当前实现见 [表盘工程](../watchface/README.md)：紧凑大圆点时钟位于上半屏，下方点阵血糖居中，左侧原始测量时间、右侧趋势箭头，无单位和曲线；顶部紧凑日期，底部电量和心率图标文本。

0.1.10 本轮仅覆盖 ID `8670260101` 的 Ottai Ultra，布局唯一参数源为 [layout.json](../watchface/layout.json)：6×14/90×232 时钟，y=68..300，小时白色、分钟 `#ff682b`，无冒号；5×7 稀疏血糖 y=352 居中，左亮时间 y=365、右趋势 y=353，日期/电量/心率不变。Barlow 仅用于桌面预览与 unknown 问号，其余标签用设备 MiSans；不分发原厂素材。以后不同风格可用独立 ID 并存并共用数据文件与 RPK，本轮不提供第二款。

当前设备已完成独立 ID 安装、布局目视、通知图标及历史短锁屏自然更新。手机 0.1.11 已完成恢复补传及两个镜像持续后台的自然周期文件导出；后一轮屏显待用户确认。新环境必须以通知无积压、自动唤起和完整身份文件回执复验，不能只读旧文件。断连、旧数据标记、休眠恢复、长按换表盘、其他页面行为、长期稳定性、AOD 和耗电尚未完整验收。详见 [验证记录](validation.md)。

追加需求只调整颜色，保留已确认布局：按用户自定义显示分段，3.9–7.8（含）紫色、大于 7.8 至 12.0（含）黄色，其余有效值红色；数值与趋势同步，旧数据同色系变暗且保留 OLD。动态配色已安装，三色/边界/过期分支桌面验证通过；本次未额外取得真实范围切换的目视证据。规则和证据边界见[表盘工程](../watchface/README.md#用户自定义显示颜色)。
