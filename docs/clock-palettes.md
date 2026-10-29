# 时钟配色与切换时段

0.1.13 开发候选，仅 Ottai Ultra 点阵款使用分时随机双色；Signal 与 Meridian 使用各自固定的协调主题。当前真机仍为 0.1.12，0.1.13 尚未安装，待最后统一调试。

## 选择规则

- 当地时间 **04:00、11:00、15:00、19:00** 换组，分别对应 04–11、11–15、15–19、19–次日04；午夜不换组。
- 整组选取小时/分钟双色，同段重新加载、抬腕或重启渲染仍相同，相邻段不重复；不是独立随机两种颜色。
- 使用当地公历日期与四个时段作稳定伪随机种子；相邻时段在两个交错的配色组中选取，无额外持久化。
- 复用可见时 15 秒检查与亮屏立即刷新，息屏暂停。不增加传感器轮询、蓝牙请求或定时器。

## 重新筛选的配色依据

根据 Color Hunt 已发布组合取色，采用柔和中性色与同调强调色，移除原来的霓虹青莓、强蓝橙和高饱和朱红组合。协调性是人工设计取舍，黑底对比度仅负责可读性，不能独自证明美观。Coolors 的调色板和趋势页在本轮访问返回 403，因此没有把未读取到的内容列作取色依据。

颜色及出处的唯一数据源为 [palettes.json](../watchface/palettes.json)。部分色组来自 Color Hunt 分类页可核对的已发布列表，不虚构独立调色板链接。

| 主题 | 小时 / 分钟 | 来源 |
| --- | --- | --- |
| 珍珠青瓷 | `#EEEEEE` / `#76ABAE` | [Color Hunt](https://colorhunt.co/palette/22283131363f76abaeeeeeee) |
| 象牙鼠尾草 | `#FEFAE0` / `#CCD5AE` | [Color Hunt](https://colorhunt.co/palette/ccd5aee9edc9fefae0faedcd) |
| 雾蓝瓷白 | `#D6E6F2` / `#769FCD` | [Color Hunt](https://colorhunt.co/palette/f7fbfcd6e6f2b9d7ea769fcd) |
| 柔雾藤紫 | `#F4EEFF` / `#A6B1E1` | [Color Hunt](https://colorhunt.co/palette/f4eeffdcd6f7a6b1e1424874) |
| 暖灰玫瑰 | `#F5EBEB` / `#D5B4B4` | [Color Hunt](https://colorhunt.co/palette/867070d5b4b4e4d0d0f5ebeb) |
| 丝绸浅粉 | `#F9F5F6` / `#F2BED1` | [Color Hunt](https://colorhunt.co/palette/f9f5f6f8e8eefdcedff2bed1) |
| 海雾兰紫 | `#C0DBEA` / `#BA90C6` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 杏砂奶油 | `#F9F3DF` / `#FFC898` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |

16 个时钟基色与实际黑底的最低 sRGB 对比度约 **7.611:1**，高于构建门槛 4.5:1。小时/分钟不相互叠印，因此不把双色彼此的对比度当成文本与背景对比度。Ultra 保持黑底、原点阵形状及布局。

日期与血糖原始更新时间统一 `#B9C2C8`，包括旧数据的时间；仍保留 `OLD`，血糖值与趋势在原有紫/黄/红色系中变暗，不改变原始测量时间。

Signal 采用珍珠白/青瓷实心数字和暗色信息卡；Meridian 采用暖象牙时针/灰青分针，黑底刻度。设计参考主流表盘的数字模块与传统指针两类信息层级，例如 [Apple 的 Modular / Simple / California 类型](https://support.apple.com/en-euro/guide/watch/apde9218b440/27/watchos/27)；未复制其素材或专有字体。

## 验证边界

四个时间边界、午夜、跨年/闰日、夏令时、同段重载、息屏跨段恢复及原血糖数据/过期规则已通过本地 Lua 测试。构建检查所有颜色、资源路径、ID、Lua 主入口及三款全天每分钟的时钟资源。

预览是合成数据；字体在真机使用系统 MiSans 的日期/指标与打包的数字位图，桌面字体度量不能代替真机核对。0.1.13 的三款加载、选择器并存、字体位置与真实读数更新均待统一真机调试；此前 0.1.12 安装验收不可移作本轮结果。历史 06/14/22 与旧配色库见 [旧记录](https://github.com/joviliu/ottai_watch/blob/0b77ed7/docs/clock-palettes.md)。
