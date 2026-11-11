# Signal 0.1.20：底部圆角裁切修复

2026-11-11。本版只覆盖 Signal `8670260102`。用户在 0.1.19 实机发现底部 OLD 部分超出圆角、LAST UPDATE 左端字母被裁切，因此仅修补这两处：

- Signal 不再显示 OLD，原始测量时间仍以灰色 `HH:MM` 保留；超过 10 分钟的血糖与趋势仍按原规则变暗，不改变数据有效期或伪造新鲜读数。
- 静态 LAST UPDATE 标签向右移动 8px（x=30→38，y=464 保持），避开左下圆角。
- 原 32 组时钟配色、Poiret One 字体/数字素材及其余布局保留；04/11/15/19 选择与 float32/int32 精度修复保持。

Ultra 和 Meridian 继续使用已获用户确认的 [0.1.19](../0.1.19/README.md) 冻结制品，本次不覆盖这两款。手机/Mac 0.7.1、RPK 0.1.12 与既有绑定保持。

BIN 为 **2,651,852 字节、767 个资源**，SHA-256 `a8c050b5d76b75cf603afea1f5a7b232fce5f24cda3cd84c6baa8d2a1b8c2d06`。本目录包含 BIN/ZIP、manifest、实际打包的 layout、冻结原色库，以及三份合成预览；先核对 `SHA256SUMS`。预览不是个人健康数据或实机屏摄。

## 验收与恢复状态

本地验证通过：帧协议、上海/纽约双时区 Lua UI，以及三款当前资源/打包检查；Signal 标签实际像素恰好右移 8px、无 OLD、灰色原始时间和过期数值/箭头变暗均已覆盖。三款精度回归此前各 1,152 个案例在桌面/float32/int32 Lua 中一致，本补丁未改选色器。发布 BIN/ZIP、manifest、layout 与色库已核对；相对 Signal 0.1.19 仅 main.lua 和 background.png 改变，冻结的 Ultra/Meridian 0.1.19 制品保持。

Signal 0.1.20 已于 23:35:05 完成 100% 上传、INSTALL_OK 与 DISCONNECTED，临时安装器随后成功卸载。用户随后回复“Signal UI正常”，底部 OLD 移除与 LAST UPDATE 圆角修补已完成屏显验收。

用户已自行安装并登录官方 `com.mi.health` 3.59.2/code359002，包默认启用；镜像已实际绑定官方 WearableXmsService，两端 FGS、原通知访问与实际监听绑定已核对。官方 POST_NOTIFICATIONS 恢复为此前允许状态，蓝牙/位置授权未改；厂商“无限制”已在 UI 核对，双方 Android idle 豁免保持。

用户已重新连接官方 HC 并允许五项写入、手动同步设备；镜像 HC 已重新启用并完成最近 48h 同步。Ali 只读快照已更新，HC 与手机步数两个来源可用，原睡眠、锻炼、心率和活动能量记录仍在。此处证明授权、快照同步与既有资料保留，不把旧记录当作新采集记录。 修改版与临时安装器均已查询确认不存在，安装器私有认证输入随卸载移除；既有手表绑定与 RPK 保持。

观察起点之后的一条自然新测量已匹配 FACE_EXPORT，Ali 最新读数也与该源测量对应且上传已更新；收到时手机为锁屏 Dozing，观察期间未手动打开两端镜像。USB 仍连接，因此不属于非充电验收；源时间仅有分钟粒度，不计算传感器至表盘的端到端延迟。本轮没有新增两周期、重启、多日、AOD 或耗电结论。

最终源码 `765c3bafad7ad86d84a995c78defc65c66dd5e75` 的 [CI 43051875173](https://github.com/joviliu/ottai_watch/actions/runs/43051875173) 在 Linux/macOS 均通过。跨平台 PNG 回归比较解码后的像素，构建固定 Pillow BASIC 字体布局；已确认的 Mac 构建表盘素材像素与冻结发布制品保持，不以 PNG 编码字节差异判定视觉变化。 [最新交接](../../docs/HANDOFF.md)
