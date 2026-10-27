# 时钟的协调双色随机配色

表盘 0.1.12 只改变时钟图片的颜色。字号、圆点形状、位置、日期、电量、心率以及血糖数值/趋势的紫黄红规则沿用既有版本，黑色背景保持不变。

## 选择规则

- 以手表当地时间的 **06:00、14:00、22:00** 为切换点，每组保持 8 小时；午夜仍沿用前一天 22:00 的选择。
- 从下面的已配对方案中整体选取小时/分钟双色。配色依据为原始调色板、主题关系和实际黑底可读性，风格范围开放。
- 使用当地公历日期及时段作为稳定伪随机种子；同一时段内抬腕、重新打开或重新加载表盘都得到相同选择。相邻时段从交错的两组中选取，保证不重复；没有固定的每日三色顺序。
- 复用原有可见时 15 秒刷新和亮屏立即刷新，息屏暂停。没有新增定时器、联网、蓝牙通信或持久化写入。

这是一种可复现的伪随机选择，不是密码学随机。调整配色库或算法会改变相应时段的选择结果。

## 配色依据

以下为小时色 / 分钟色。原色取自相应已发布调色板，双色取舍与中文主题命名由本项目整理；时钟仍使用原创点阵素材。

| 主题 | 小时 / 分钟 | 搭配依据 | 原始调色板 |
| --- | --- | --- | --- |
| 白橙经典 | `#F5F5F5` / `#FF682B` | 中性色与暖色强调 | 已确认的原表盘方案 |
| 玫瑰奶油 | `#FAE8E0` / `#EF7C8E` | 暖奶油与柔和玫瑰色 | [Canva Rosettes and Cream](https://www.canva.com/colors/color-palettes/rosettes-and-cream/) |
| 像素蓝橙 | `#41A6F6` / `#EF7D57` | 冷蓝与柔暖橙对比 | [Sweetie 16 — GrafxKid](https://lospec.com/palette-list/sweetie-16) |
| 银灰杏粉 | `#B9B7BD` / `#E7D2CC` | 低饱和灰与暖杏粉 | [Canva Room for Comfort](https://www.canva.com/colors/color-palettes/room-for-comfort/) |
| 霓虹青莓 | `#2FF3E0` / `#FA26A0` | 鲜明青色与莓粉对比 | [Canva Retro Punch](https://www.canva.com/colors/color-palettes/retro-punch/) |
| 象牙鼠尾草 | `#FEFAE0` / `#CCD5AE` | 暖象牙与自然灰绿 | [Color Hunt](https://colorhunt.co/palette/ccd5aee9edc9fefae0faedcd) |
| 冰蓝兰紫 | `#C8F4F9` / `#C26DBC` | 浅冰蓝衬兰紫 | [Canva Icy Gradient](https://www.canva.com/colors/color-palettes/icy-gradient/) |
| 薄荷粉糖 | `#B4F8C8` / `#FFAEBC` | 柔和薄荷与浅粉 | [Canva Pastel Dreams](https://www.canva.com/colors/color-palettes/pastel-dreams/) |
| 暮蓝莓紫 | `#249FDE` / `#BC4A9B` | 明亮蓝与莓紫 | [AAP-64 — Adigun A. Polack](https://lospec.com/palette-list/aap-64) |
| 青瓷淡紫 | `#85D2D0` / `#887BB0` | 低饱和青瓷与淡紫 | [Canva Pastel Blonde](https://www.canva.com/colors/color-palettes/pastel-blonde/) |
| 琥珀朱红 | `#FDB750` / `#FC2E20` | 相近暖色的明度与色相区分 | [Canva Warm Sunset](https://www.canva.com/colors/color-palettes/warm-sunset/) |
| 奶白莓粉 | `#EFEBE0` / `#FB6B90` | 奶白中性色与莓粉强调 | [Canva Sweet Cotton Sugar](https://www.canva.com/colors/color-palettes/sweet-cotton-sugar/) |

构建时分别计算每个基色与实际黑背景的 sRGB 对比度，要求至少 4.5:1；当前最低约 4.591:1。该数值用于筛除难辨识的组合，不能代替手表亮度、环境光和点阵渲染的实机观察。黑底让全部候选及既有血糖信息共用已验证的背景，当前无需增加背景换色。

配色常量集中在 `watchface/build.py` 的 `CLOCK_PALETTES`，生成 240 张时钟 PNG 与 `clock-palettes.lua`。当前 BIN 为 2,673,172 B、366 项资源，沿用单款 ID `8670260101`；Lua 入口按名字定位并在打包往返后校验。

## 验证与安装边界

已通过帧/UI测试、06/14/22边界、午夜、年末、闰日、夏令时重复时刻、同分钟缓存、同段重新加载稳定和息屏跨段恢复测试；原血糖分段、旧数据、布局与暂停逻辑回归通过。24 个基色的黑底对比度、全部数字尺寸和透明轮廓均检查通过。

预览包含合成示例，不是实机截图；安装缩略图使用血糖占位。桌面测试未代替 366 项资源在当前固件的加载或真实跨 8 小时切换目视；实机状态见 [0.1.12 发布说明](../releases/0.1.12/README.md)。
