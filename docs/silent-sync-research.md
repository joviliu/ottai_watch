# 减少自动同步时的界面闪现

2026-10-26。当前固件与 SDK 范围见主 README。

## 结论

优先在同一 RPK 中延迟生成主界面，连接与文件写入立即运行。自动同步完成后在主界面展示前退出；手动打开稍后正常展示，断连或写入异常有界面反馈。透明窗口作为实机试验，不能预先承诺无感。

当前 Android SDK 的 `launchWearApp` 只接受设备、包名和回调，没有路由或启动参数。仅增加一个同步页不能让手机直接选择它。收到本次实时消息的 `watchfaceSync` 才能确定同步意图，缓存里的同名字段不能作为本次启动原因。

## 官方接口范围

- [颜色配置](https://iot.mi.com/vela/quickapp/zh/components/general/color.html) 支持 `transparent`、RGBA 和 `#rrggbbaa`。[manifest](https://iot.mi.com/vela/quickapp/zh/guide/framework/manifest.html) 公开 `display.backgroundColor`。这只确认语法，不保证窗口透明时系统会保留下层表盘，也不排除转场或黑屏。
- [app.getInfo()](https://iot.mi.com/vela/quickapp/zh/features/basic/app.html) 同步返回 `source.type`，其中含 `bluetooth` 与 `shortcut`。需要在 Watch 6 分别诊断手动和自动启动，未确认前不能用它决定隐藏；热启动来源是否刷新也未获保证。
- [后台运行](https://iot.mi.com/vela/quickapp/zh/guide/framework/other/background-running.html) 列出音频、请求和定位等实际后台能力，未找到面向本需求的无窗口 service 或 interconnect 常驻入口。未找到公开办法不等于固件绝对不支持。
- [interconnect](https://iot.mi.com/vela/quickapp/zh/features/network/interconnect.html) 面向 JS 应用。未找到官方公开的 Lua 表盘直接接收任意手机数据接口。

另建一个应用仍受窗口和生命周期限制，还需另行验证 SDK 包名配对、通信通道、私有文件路径及表盘读取路径；目前没有证据表明它能消除系统转场。因此不先拆第二个 RPK，也不申请无关音频/定位能力保活。

## 试验版范围

RPK 0.1.9 / code 10 候选在原入口添加启动门控：初始约 2 秒不绘制主界面，本次实时同步帧到达则继续等待匹配文件导出并返回；手动打开、离线、写入失败或等待超时后显示原界面。保留完整帧身份、异步发布和新帧取消旧退出的保护。已展示的手动界面不重新隐藏。

固定延迟仍有边界：若同步标志比门控更晚到达，主界面可能先出现；即使主内容完全不生成，系统窗口也可能出现。

[试验包](../releases/watch-0.1.9/README.md) 已完成测试、构建和独立审查，证书与基线一致，曾通过 Mi Fitness 安装成功。用户手动启动确认先黑屏、随后主界面正常，透明窗口没有透出下层表盘。随后两轮新测量有手机接收、唤起请求及 SDK accepted，但无文件导出回执，用户未观察到自动更新；镜像进程未被冻结。失败原因未定位，不能单独归因某个 UI 属性。此方案未通过验收，已撤回，不称为无感方案。

当前源码恢复 0.1.8 界面/同步逻辑，递增为 [RPK 0.1.10 / code 11](../releases/watch-0.1.10/README.md)，已覆盖安装并重建手机 SDK 通道。两次旧测量恢复/状态更正已自动导出并回执，用户确认正常返回表盘和原始时间匹配；上游测量时间未推进，回退后的新自然周期未验。编译入口页与旧包一致，app.js 只差嵌入版本信息；手机 0.1.11 与现有表盘未改变。回退和重连共同执行，不能单独确定失败原因。试验增量和测试见 [归档](../experiments/watch-transparent-0.1.9/README.md)。

进一步检查没有给出通信保活的依据：当前 AIoT 工具链对 `config.background` 仅验证对象类型，能打包不代表固件支持 `system.interconnect` 后台运行；公开 [interconnect 实现](https://github.com/open-vela/frameworks_runtimes_feature/blob/dev/modules/interconnect_impl.cpp) 的销毁路径关闭 miwear 通道，未发现该模块申请后台保活。此代码与本机固件不等价，只能界定公开证据范围，不能断言硬件绝对不支持。没有据此申请无关音频、定位或调用内部接口。

验收需分别检查自动同步不露主界面且数据推进、主动打开延迟后正常显示、断连缓存、写入失败诊断与超时、息屏/离页定时器清理。桌面测试无法验证透明合成或转场视觉。
