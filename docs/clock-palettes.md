# 时钟配色与切换时段

2026-11-11：[0.1.19](../releases/0.1.19/README.md) 改为每款独立 32 组色库，沿用 0.1.18 精度修复后的同一个时段选择器。Meridian/Ultra 已上传且用户已确认；其他本轮验收与客户端恢复状态见[交接](HANDOFF.md)。

| 款式 | 配色数据 | 结构 |
| --- | --- | --- |
| Signal | [palettes.json](../watchface/palettes.json) | 原 32 组名称、顺序、色码及来源不变 |
| Meridian | [palettes-meridian.json](../watchface/palettes-meridian.json) | 16 金属色调 + 16 鲜艳塑料色调 |
| Ultra | [palettes-ultra.json](../watchface/palettes-ultra.json) | 24 运动 + 8 商务；主色搭配柔和同色系/中性色，减少粉色和强烈撞色 |

新色库的原站搜索证据、直接页面访问限制、衍生配对与逐组对比度冻结于[来源清单](face-palette-sources-2026-11.md)。金属是颜色表达，不包含材质渲染。Signal 使用预着色数字，Meridian 使用原生有色对象，均不依赖真机未生效的 image recolor。

## 选择规则

- 当地时间 **04:00、11:00、15:00、19:00** 换组，分别对应 04–11、11–15、15–19、19–次日04；午夜不换组。
- 整组选取小时/分钟双色，同段重新加载、抬腕或重启渲染仍相同，相邻段不重复；不是独立随机两种颜色。
- 使用当地公历日期与四个时段作稳定伪随机种子；相邻时段在两个交错的配色组中选取，无额外持久化。三款各自解析自己的列表，不新增款式种子；Meridian 每个奇偶子池均有 8 金属/8 塑料，Ultra 每个子池均有 12 运动/4 商务。
- 0.1.18 改用模 65521 的小整数混合，迭代最大值 16,459,369 小于 2^24，在 float32/int32 下保持精确；随机选择仍允许隔日同一时段偶然重复，不代表每日固定循环。
- 复用可见时 15 秒检查与亮屏立即刷新，息屏暂停。不增加传感器轮询、蓝牙请求或定时器。

## Signal 保留的原 32 组

保留 0.1.13 中用户认可的原 8 组，再增加 24 组，共 32 组。根据 Color Hunt 已发布组合取色，采用柔和中性色与同调强调色，移除原来的霓虹青莓、强蓝橙和高饱和朱红组合。协调性是人工设计取舍，黑底对比度仅负责可读性，不能独自证明美观。Coolors 的调色板和趋势页在本轮访问返回 403，因此没有把未读取到的内容列作取色依据。

Signal 颜色及出处的数据源为 [palettes.json](../watchface/palettes.json)。部分色组来自 Color Hunt 分类页可核对的已发布列表，不虚构独立调色板链接。

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

各款 64 个时钟基色均逐个与黑底比较，构建门槛为 4.5:1；Signal 最低约 5.756:1、Meridian 4.849:1、Ultra 5.495:1。小时/分钟不相互叠印，因此不以双色彼此的对比度代替文字与背景的可读性。协调性属于人工设计取舍，不能由对比度或饱和度门槛单独证明。

Ultra 保留原大时钟圆点字形，血糖/箭头改为统一 8px LED 栅格，未亮点为暗灰并保留黑色点间隙。底部原始测量时间、电量、心率均为 MiSans-Regular 28px、同一行高、三等宽区域；OLD 独立置于时间上方。Signal 保留 Poiret One 原比例数字，[0.1.20](../releases/0.1.20/README.md) 仅去掉底部 OLD 并将 LAST UPDATE 右移，原色库与灰色测量时间、过期变暗规则不变；Meridian 保留原指针、指标坐标、浅灰血糖与淡色箭头。血糖分段颜色与原始测量时间不随时钟配色变化。

## 验证边界

现有本地回归覆盖四个时间边界、午夜、跨年/闰日、夏令时、同段重载、息屏恢复、全部配色可达、原血糖/过期规则，以及 float32/int32 数值一致性。资源检查逐款核对打包色库、实际像素色、全天每分钟引用与对象边界，并冻结 Signal 素材/布局和 Meridian 非配色资源。

本轮最终测试结果与设备安装状态以 [0.1.19 发布记录](../releases/0.1.19/README.md)为准。预览是合成数据；桌面字体度量、低精度 VM 及逻辑测试不能代替真实跨时点、多日颜色、屏显、AOD 或耗电验证。历史 06/14/22 与旧配色库见[旧记录](https://github.com/joviliu/ottai_watch/blob/0b77ed7/docs/clock-palettes.md)。
