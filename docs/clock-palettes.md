# 时钟配色与切换时段

2026-10-30：已发现并修复跨日选色的低精度兼容缺陷，三款 [0.1.18](../releases/0.1.18/README.md) 已构建、尚未真机安装。32 组颜色与全部布局保留。当前设备实际 Lua 编译配置未知，以下复现说明代码风险，不等同于真机现场根因已直接测定。

0.1.16 两款与现有 Ultra 共用 32 组协调双色。实机已确认 0.1.15 的图片 recolor 未生效，因此本版 Signal 改为 32 组预着色数字，Meridian 用原生有色对象组成指针，移除静默固定色回退。两款当前时段的实际配色已由用户确认，完整验收边界见 [交接记录](HANDOFF.md)。

## 选择规则

- 当地时间 **04:00、11:00、15:00、19:00** 换组，分别对应 04–11、11–15、15–19、19–次日04；午夜不换组。
- 整组选取小时/分钟双色，同段重新加载、抬腕或重启渲染仍相同，相邻段不重复；不是独立随机两种颜色。
- 使用当地公历日期与四个时段作稳定伪随机种子；相邻时段在两个交错的配色组中选取，无额外持久化。
- 0.1.18 改用模 65521 的小整数混合，迭代最大值 16,459,369 小于 2^24，在 float32/int32 下保持精确；随机选择仍允许隔日同一时段偶然重复，不代表每日固定循环。
- 复用可见时 15 秒检查与亮屏立即刷新，息屏暂停。不增加传感器轮询、蓝牙请求或定时器。

## 重新筛选的配色依据

保留 0.1.13 中用户认可的原 8 组，再增加 24 组，共 32 组。根据 Color Hunt 已发布组合取色，采用柔和中性色与同调强调色，移除原来的霓虹青莓、强蓝橙和高饱和朱红组合。协调性是人工设计取舍，黑底对比度仅负责可读性，不能独自证明美观。Coolors 的调色板和趋势页在本轮访问返回 403，因此没有把未读取到的内容列作取色依据。

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
| 亚麻鼠尾草 | `#FEFAF3` / `#B8CFB3` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 雾紫花瓣 | `#C5B3D3` / `#F5CBCB` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 青柠冰蓝 | `#F6FFDC` / `#CFECF3` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 奶油蜜桃 | `#FFEABB` / `#FBC3C1` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 暖纸珊瑚 | `#FEEAC9` / `#FD7979` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 瓷白鸢尾 | `#FEEBF6` / `#687FE5` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 桃色云朵 | `#FFF2EB` / `#FFD6BA` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 水青兰紫 | `#A6D6D6` / `#8E7DBE` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 樱草薄荷 | `#F4F8D3` / `#A6D6D6` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 象牙烟紫 | `#FFF7F3` / `#C599B6` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 桃绒玫瑰 | `#FAD0C4` / `#E6B2BA` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 奶黄鸢尾 | `#FBF3B9` / `#B7B1F2` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 蜂蜜丁香 | `#FFF9BF` / `#CB9DF0` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 杏粉缎面 | `#FDDBBB` / `#F0C1E1` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 奶油长春花 | `#FFF6E3` / `#CDC1FF` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 冰川淡紫 | `#BFECFF` / `#CDC1FF` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 亚麻橄榄 | `#EDE8DC` / `#A5B68D` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 燕麦浅玫 | `#C1CFA1` / `#E7CCCC` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 杏色兰花 | `#FFEBD4` / `#F0A8D0` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 象牙浅玉 | `#F7F9F2` / `#91DDCF` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 珍珠胭脂 | `#F6F5F2` / `#F3D0D7` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 暖白干玫 | `#FFF8E3` / `#E6A4B4` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 粉瓷灰绿 | `#FFEEF4` / `#94A684` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |
| 瓷白丁香 | `#FAF3F0` / `#DBC4F0` | [Color Hunt](https://colorhunt.co/palettes/pastel-light-pink) |

64 个时钟基色与实际黑底的最低 sRGB 对比度约 **5.756:1**，高于构建门槛 4.5:1。小时/分钟不相互叠印，因此不把双色彼此的对比度当成文本与背景对比度。Ultra 保持黑底、原点阵形状及布局。

日期与血糖原始更新时间统一 `#B9C2C8`，包括旧数据的时间；仍保留 `OLD`，血糖值与趋势在原有紫/黄/红色系中变暗，不改变原始测量时间。

Signal 当前采用 Poiret One 原比例数字与紧凑信息行；Meridian 采用全宽圆盘，底部以固定浅灰血糖替换心率，箭头独立使用淡绿/淡黄/淡红，过期用暗灰。两款时钟选用同一分时双色，血糖指标不随时钟选色变化。设计参考主流表盘的数字模块与传统指针两类信息层级，例如 [Apple 的 Modular / Simple / California 类型](https://support.apple.com/en-euro/guide/watch/apde9218b440/27/watchos/27)；未复制其素材或专有字体。

## 验证边界

四个时间边界、午夜、跨年/闰日、夏令时、同段重载、息屏跨段恢复及原血糖数据/过期规则已通过本地 Lua 测试。构建检查所有颜色、资源路径、ID、Lua 主入口及三款全天每分钟的时钟资源。

预览是合成数据；字体在真机使用系统 MiSans 的日期/指标与打包的数字位图，桌面字体度量不能代替真机核对。0.1.14 三款已上传并逐款确认显示；RPK 0.1.12 + 0.1.15 Meridian 已完成非充电锁屏两轮自动更新；0.1.16 的新布局和配色另行实机确认，不移用此前固定色结果。历史 06/14/22 与旧配色库见 [旧记录](https://github.com/joviliu/ottai_watch/blob/0b77ed7/docs/clock-palettes.md)。
