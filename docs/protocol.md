# 数据与时序

```
Ottai com.ottai.tag 通知
  → OttaiMetadataListener → Reading / ReadingStore
  → BridgeService → Mi Fitness Wearable SDK → 蓝牙
  → Vela system.interconnect → model.js → 展示 / 缓存 / ACK
```

`sourceAt` 是通知正文 HH:mm 对应的测量时间，依据通知原始时间锚定日期并处理跨午夜；`receivedAt` 才是手机接收时间。不要用到达时间覆盖测量时间。拒绝乱序、明显未来、非法单位和值；未提供趋势时显示 `?`，不要推测。

下列数据为合成示例，不是用户读数：

```json
{
  "type": "glucose", "version": 1,
  "value": 6.8, "unit": "mmol/L", "trend": "↗",
  "sourceAt": 1792972800000, "source": "ottai_notification",
  "receivedAt": 1792972805000,
  "history": [{"time": 1792972800000, "value": 6.8}]
}
```

`system.interconnect.send({data: ...})` 的 `data` 必须为 **Object**。接收事件的 `event.data` 才是 JSON 字符串；把发送端 data 改为 JSON 字符串会触发类型错误。

手表消息类型还包括 `request_latest` 与 `ack`；以实际 `index.ux` / `BridgeService.java` 为准。ACK 包含对应帧的 `sourceAt`，手机只承认当前帧的回执。SDK success 仅说明传输调用成功；首次当前帧 ACK 和最近 ACK 分开记录。ACK 说明应用处理过该帧，不能证明屏幕在用户未观察时实时可见。

手机保留最多 24 个真实点；曲线不跨越超过 10 分钟的缺口。手表每分钟只更新前台年龄文本；进入、连接恢复时各请求最新帧。Vela 应用退后台时的运行与送达受固件限制，因此当前实现不能承诺表盘状态下每 5 分钟后台更新。重新打开后先显示缓存，数秒内同步最新数据是已观察到的行为。
