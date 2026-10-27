# 换回官方小米运动健康的兼容性

2026-10-27。本轮已在用户确认同步后完成客户端替换：备份校验 Mi Fitness mod 3.33.6i m0tral v141、暂停镜像，卸载 `com.xiaomi.wearable`，安装国行官方 `com.mi.health` 3.59.2。官方已恢复连接设备，无解绑、重置或重装 RPK/表盘；本组合的锁屏、非充电两轮新测量自动投递及最后一轮表盘目视已通过。

## 结论

**本组合的官方客户端日常同步实测通过**：手机镜像 0.1.11、手表 RPK 0.1.10、表盘 0.1.12，配合国行官方 3.59.2，完成两轮新测量自动导出/ACK 与最后一轮用户目视。启动补传不计这两轮，此前修改版结果也单独作为历史证据。官方客户端下的新装、未来 RPK 升级侧载入口、换版后再次重启和多日稳定性未验证。

### 本轮实测结果

- 已完成先同步、保留可回退修改版安装包及校验，再卸载修改版、安装官方 3.59.2。既有连接设备已恢复，手表 RPK 0.1.10 和表盘 0.1.12 均保留，镜像手机仍为 0.1.11。
- 官方 `BLUETOOTH_CONNECT`、`BLUETOOTH_SCAN`、`POST_NOTIFICATIONS` 已授予；官方新 listener 与镜像原 listener 都有通知访问授权。官方 `NotifySyncService` 的 `AppBindRecord` 另显示 `:system` 与 `NotificationListenerService` intent，已确认实际系统绑定。两应用的 Android 与厂商运行时豁免均实际存在。
- 镜像启动后，官方 `WearableXmsService` 的服务状态已显示镜像绑定；启动补传取得 `FACE_EXPORT` 和 ACK。这是当前安装/绑定/补传证据，不把静态接口匹配直接算作成功。
- 两条原始测量时间及各自通知时间均在正式测试起点之后，源测量时间严格相差 300000 ms；每条仅一个通知元数据事件，无同源更正或重发混淆。日志已核对 `observedAt <= FACE_WAKE <= FACE_EXPORT <= ACK`，完整身份文件回执匹配当前读数，启动补传不计入。
- 每 45 秒采样均为两应用 FGS 后台、屏幕 Dozing、非充电，Android/厂商两项派生豁免保持；无两应用新增冻结、采样连接错误或 SDK 错误，镜像进程保持同一个实例。采样不能外推为多日可靠性。
- 用户未手动打开手机或手表镜像，仅抬腕确认最后一轮原始测量时间一致、正常停留表盘；本轮没有源码改动。

| 正式周期 | 通知处理 | 自动唤起 | 完整身份文件导出 | CPU 持有至提前释放 | ACK |
| --- | --- | --- | --- | --- | --- |
| 第一轮 | 12 ms | 8.017 秒 | 9.900 秒 | 9.899 秒 | 9.949 秒 |
| 第二轮 | 8 ms | 8.017 秒 | 9.749 秒 | 9.747 秒 | 9.803 秒 |

唤起、导出和 ACK 耗时从镜像收到通知算起，CPU 列为实际持有时长；不是测量至屏显的端到端时延。

**未验范围**：此次沿用既有 RPK/表盘，官方客户端的新装和未来 RPK 升级侧载入口仍待单独验证；换版后没有再次重启或进行多日观察，不能将此前修改版阶段的重启保持结论迁移到官方客户端。

### 已确认的接口与登记机制

- 国行官方 3.59.2 的包名为 `com.mi.health`，修改版为 `com.xiaomi.wearable`。两者均提供 `WearableXmsService` 与相同的 `com.xiaomi.wearable.XMS_WEARABLE_SERVICE` action；服务导出层未见额外权限门槛。
- 本仓库 `ApiClient.openService()` 已优先寻找 `com.mi.health`，再寻找 `com.xiaomi.wearable`，因此换成国行包名本身不要求先改桥接代码。
- 两版的设备能力检查均依据 `thirdparty_app` 或 `third_party_no_market`；检查实现没有发现修改版强制放开的差别。
- 两版均以手机调用包名、设备 ID、已安装 RPK 指纹与手机 APK 签名进行校验，消息注册、发送和唤起都经过该校验；部分能力另需通信授权。本项目 Android/RPK 已使用相同包名与签名。
- 官方连接成功后存在从手表查询已安装应用列表、映射 `packageName/fingerprint`、同步至本地 `WatchAppRepository` 的完整路径。因此，新客户端数据库不必依赖在该客户端内重新安装过 RPK 才能产生登记。

### Binder 与序列化的静态匹配范围

- 主接口 descriptor 为 `com.xiaomi.xms.wearable.IWearableInterface`。官方与当前 SDK 的前 15 个事务号及布局匹配；官方在末尾追加事务 16–18，未把既有事务向后移位。
- 本项目已用范围内核对的事务 2/3/4/5/7/11/12，分别为 `checkPermission`、`checkPermissions`、`requestPermission`、`getConnectedNodes`、`launchWearApp`、`sendMessage`、`addListener`；参数顺序及所用回调静态匹配。
- 已用 Parcelable 布局匹配：`Node` 为两个 String，`Status` 为 int，`Permission` 为 String；消息监听 `IMessageListener` 的事务 1 为 String + byte[]。这些检查覆盖当前调用方式，不代表追加接口或所有未来 SDK 均兼容。
- 官方通知访问 listener 的完整组件为 `com.mi.health/com.xiaomi.fitness.notify.NotifySyncService`；本轮已分别确认通知访问授权及实际系统绑定，不能沿用修改版组件名。官方启动入口为 `com.mi.health/com.xiaomi.fitness.login.SplashActivity`。

这些是所检查版本的静态实现证据，不代替当前设备上的应用列表返回、实际 IPC 调用、登录、通知监听及蓝牙连接恢复验证。

## 分开看运行、缓存与安装

| 部分 | 换版时需要确认 |
| --- | --- |
| 表盘时间与外观 | 在手表本地运行；只看这些正常不能证明手机通信正常 |
| 血糖缓存 | 表盘读取已导出文件，旧值会保留并按原始时间标记 `OLD`；旧值仍可见不能当作新更新 |
| 新血糖 | 官方下两轮新测量自动完整身份导出/ACK已通过，最后一轮原始时间和表盘状态已由用户确认 |
| 已装 RPK/表盘 | 本次无解绑/重置，RPK 与表盘均保留，未重装；不据此保证重置后仍保留 |
| 新装/后续开发包升级 | 本次没有重装 RPK；调试辅助脚本面向修改版，官方侧载入口未验。表盘有既有 SPP 工具，但本次换版验收未升级 RPK/表盘 |

本轮用户已确认同步，已保留可回退安装包及本地开发凭据，并恢复官方连接及必要授权。两个测试起点后的新测量已在镜像持续后台时自动投递，取得完整身份文件回执与用户最后一轮目视。缓存通知、启动补传和解锁后补收未计入两轮验收。

## 官方资料与证据边界

- [官方 interconnect 文档](https://iot.mi.com/vela/quickapp/zh/features/network/interconnect.html)要求 Android 与 RPK 包名、签名一致。
- [官方 SDK 1.4 接口文档](https://vela-docs.cnbj1.mi-fds.com/vela-docs/files/%E5%B0%8F%E7%B1%B3%E7%A9%BF%E6%88%B4%E7%AC%AC%E4%B8%89%E6%96%B9APP%E8%83%BD%E5%8A%9B%E5%BC%80%E6%94%BE%E6%8E%A5%E5%8F%A3%E6%96%87%E6%A1%A3_1.4.pdf)列出设备发现、授权、消息收发、唤起和服务连接。所读文档未注明必须上架或云白名单；这不足以保证每个客户端/固件组合。
- [Watchdrip-Xiaomi 作者说明](https://github.com/miguelavh/Watchdrip-Xiaomi#readme)要求其方案使用修改版。该说明用于理解其安装环境，不能直接证明本项目已装 RPK 在 Watch 6 原版上一定无法通信。

本轮已完成获授权的客户端替换、设备连接恢复、两轮后台新测量投递及最后一轮表盘目视；结论只覆盖上述实测版本与条件，不外推新安装、未来升级、再次重启或多日稳定性。未修改认证检查。第三方 APK、反汇编中间文件与个人运行日志仅保留在仓库外。
