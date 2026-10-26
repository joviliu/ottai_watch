# Watch 6 小部件、手势与血糖表盘调研

调研日期：2026-10-26。实机固件 3.100.043。结论中的「未找到」表示公开资料与当前代码核查的边界，不等于硬件永远不支持。

## 结论

1. **上滑小部件是系统功能，但当前未找到可确认接入的第三方注册/数据提供接口。** 不把本应用普通页面声明成一个「小部件」后就声称已经支持。
2. **自定义表盘有真实 Watch 6 的 Lua 源码和构建工具参考，值得继续走。** 但 UI 能绘制不等于能得到本应用的最新血糖。数据共享与隐藏应用的送达机制是实施前必须解决的缺口。
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
| [m0tral/EasyFace](https://github.com/m0tral/EasyFace) | 作者当前 README 明确列出 Redmi Watch 6；安装为 Windows MSI + VC++ x86 运行库 + 编译器更新 | 有工具链路线；当前 macOS 没有现成可运行的此套 Windows 编译环境 |
| [miguelavh/Watchdrip-Xiaomi](https://github.com/miguelavh/Watchdrip-Xiaomi) | README 主要覆盖 Band 8 Pro/9/10 与 Watch 4 | 不能作为 Watch 6 无需适配的证明 |
| [Watchdrip 作者说明](https://bigdigital.home.blog/2024/11/28/xiaomi-89-support/) | 既有桥接应用 + 专用表盘路线 | 可继续寻找作者表盘的数据读取实现，而非只照搬旧尺寸表盘 |
| [calinhoria/watchface-installer](https://github.com/calinhoria/watchface-installer) | 有 Watch 6 SPP 安装协议和预览解析的源码；AGPL-3.0 | 可能解决最终 `.bin` 安装，不解决实时数据；不使用其内嵌默认配对密钥或 APK |

核查的版本：`maga32` commit `6e8a21ebbe9740ba233eec3a859b657e41e595fd`；`MiWatchLuaWatchfaces` commit `5af6e14ea92830a394c88dc04f76ceef697a6ded`。

## 真正缺少的链路

1. 当前 Vela 使用 `system.storage` 保存帧。旧 WatchDrip 快应用会用 `system.file.writeText` 写 `internal://files/info.json`，但其对应 Lua 读取端源码/物理路径还未证实。
2. [官方文件组织](https://iot.mi.com/vela/quickapp/zh/features/data/file.html) 定义的是应用文件 URI；没有给出跨应用/跨表盘共享保证。不能凭猜测硬编码路径或借用别的应用包名。
3. [官方后台运行](https://iot.mi.com/vela/quickapp/zh/guide/framework/other/background-running.html) 只列出特定后台接口。即使 Lua 可以读到缓存，镜像 RPK 隐藏后是否每 5 分钟收到手机新帧，仍须实机验证。不用静音音频、持续定位等方式保活。

可行性验证应先做两个很小的实验：

- **文件实验**：单独 RPK 写固定合成标记，独立 Lua 表盘读取同一标记；成功后再接入现有合法帧，保留原始时间，不允许旧值被标成刚更新。
- **后台实验**：保持该表盘为前台，主镜像 RPK 隐藏，观察至少两个 Ottai 通知周期的 sourceAt 与回执/文件变化。若失败，必须换正式数据通道，不能把「抬腕看到缓存」算成功。

在这两项完成之前，不发布声称实时血糖功能的可安装表盘，也不重复上传静态 `.bin` 来模拟 5 分钟更新。

## 极简大数字布局草图

[布局 SVG](../watchface/minimal-layout.svg) 是原创布局草图，合成示例、非设备截图、非可安装表盘；尚未取得原厂「极简风大数字」可编辑工程，因此没有声称对原包完成改造。

建议在 432×514 黑色底上保留大时钟，下方显示 `6.8 ↗` 和 `mmol/L · 14:25`，不画曲线。趋势缺失显示 `?`；旧数据继续显示其原始时间，并在过期时降低亮度/加文字提示。亮屏恢复和真实新数据才重绘，不启用每秒刷新。最终布局可在看到原厂当前布局后精确对齐，素材不直接复制到公开仓库。

验收条件：正确安装独立 ID 表盘；数值/方向/测量时间来自真实帧；至少两次 5 分钟周期成功；断连可识别旧数据；休眠恢复正常；未破坏长按换表盘；连续运行和耗电实测后再称为可用。
