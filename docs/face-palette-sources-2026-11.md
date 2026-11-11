# Meridian / Ultra 配色来源与核验（2026-11-11）

本次只新增两套独立色库；Signal 继续使用原 `watchface/palettes.json` 的 32 组。两套新色库各 32 组，小时和分钟均以黑色背景为对比基准。

## 选色结构

- Meridian：前 16 组 `metallic`，后 16 组 `plastic`。金属组包含金、白金、铜、银、钛灰、蓝钢、青钛、铜绿与紫钛；塑料组采用鲜明的邻近色或冷暖配对。这里只表达金属色调，不引入渐变、纹理或材质渲染。
- Ultra：前 24 组 `sport`，后 8 组 `business`。运动组以明快的蓝、青、草绿、琥珀、朱砂等主色，搭配柔和同色系或低饱和中性色；蓝黄采用灰蓝与麦金。保留少量钢蓝、银灰、黄铜等沉稳配色，不取粉彩粉色。
- 保留原选择器与种子。它会按 1 基索引奇偶分组取色，因此 Meridian 两个子池均有 8 组金属与 8 组塑料；Ultra 两个子池均有 12 组运动与 4 组商务，避免风格被固定到某一时段。

## 来源与证据边界

取证日期为 2026-11-11。下表链接均是实际检索到的原站页面。Color Hunt 集合的搜索索引返回了可读取的十六进制四色组；直接打开集合页时可能只返回动态页面外壳或 “No results”。直接打开单组 Color Hunt 页面及 Coolors trending / 单色色页时出现了 403，因此没有把这些直接页面声称为已完整读取。这里冻结的是本次取得的原站搜索索引内容，不是“已完整浏览实时热门榜”的结论，也不使用由四个色码拼出的、未经验证的单组 URL。

JSON 的 `sourceColors` 保存该条使用的原始四色组或单色基色，`rationale` 说明直接取两色还是经过色调、亮度或配对调整。自定金属双档及重新调和的 Ultra 运动组明确属于本项目衍生设计，不冒充网站已有的成对作品。Ultra 的参考组虽然包含荧光色，实际输出已降低饱和度、收敛亮度，并将部分强烈互补辅色改为同色系或柔和中性色。Coolors 的色彩和谐说明只作为邻近色、互补色和明暗处理的方法参考。

| 编号 | 原站页面 | 实际取得的证据 |
| --- | --- | --- |
| CH-L | [Color Hunt · Neon Light](https://colorhunt.co/palettes/neon-light) | 搜索索引中读取到 FF9137/FFCC4D/FFFC8C/70FFD2、FF5656/FFA239/FEEE91/8CE4FF、63C8FF/4DFFBE/FDFFB8/FF2DD1 等实际四色组。 |
| CH-W | [Color Hunt · Neon White](https://colorhunt.co/palettes/neon-white) | 搜索索引中读取到 4F200D/FF8400/FFD93D/F6F1E9、40514E/2F89FC/30E3CA/F5F5F5、3D6CB9/00D1FF/00FFF0/FAFAF6 等实际四色组。 |
| CH-G | [Color Hunt · Neon Green](https://colorhunt.co/palettes/neon-green) | 搜索索引中读取到 FDFF00/9CFF2E/38E54D/2192FF、F93827/FF9D23/FFD65A/16C47F、FFCC29/F58634/007965/00AF91 等实际四色组。 |
| CH-V | [Color Hunt · Vintage Dark](https://colorhunt.co/palettes/vintage-dark) | 搜索索引中读取到 E0D9D9/5A9690/2F5755/432323、EBD5AB/8BAE66/628141/1B211A、E1D89F/D89216/374045/2C061F 等实际四色组。 |
| CH-D | [Color Hunt · Dark Grey](https://colorhunt.co/palettes/dark-grey) | 搜索索引中读取到 222831/31363F/76ABAE/EEEEEE、27374D/526D82/9DB2BF/DDE6ED 等实际四色组。 |
| CH-B | [Color Hunt · Pastel Beige Brown](https://colorhunt.co/palettes/pastel-beige-brown) | 搜索索引中读取到 F7F1DE/C4A484/B87C4C/A8BBA3、FFE6BC/E4CDA7/C3B091/8E806A、ECEBDE/D7D3BF/C1BAA1/A59D84 等实际四色组；仅用作金属色调素材，不作为粉彩塑料组。 |
| CH-S | [Color Hunt · Pastel Grey Blue](https://colorhunt.co/palettes/pastel-grey-blue) | 搜索索引中读取到 6C737E/7393A7/B5CFD8/E8ECF1、CDD5E0/89A4C7/4E709D/F5B17B、748DA6/9CB4CC/D3CEDF/F2D7D9 等实际四色组；只选冷蓝灰方向，Ultra 不取粉色。 |
| CH-M | [Color Hunt · Brown Beige Grey](https://colorhunt.co/palettes/brown-beige-grey) | 搜索索引中读取到 C36A2D/E2C275/EADCA6/F4F4F4 等实际四色组。 |
| CO-A | [Coolors · #12DFCA](https://coolors.co/12dfca) | 搜索索引可读取该亮青色页及邻近色、互补色和明暗变化的说明。用于耐力青金的主色和关系参考。 |
| CO-C | [Coolors · #00BED5](https://coolors.co/00bed5) | 搜索索引可读取该青色页及色彩和谐说明。流线青蓝由基色降低亮度并配同色系灰青；当前双色由本项目编辑，并非原页面现成配对。 |
| CO-G | [Coolors · #F6BC2E](https://coolors.co/f6bc2e) | 搜索索引可读取该金黄色页。耐力青金参考此金黄与 #12DFCA，进一步降低两色饱和度及亮度，调成柔和青绿与浅麦金；组合由本项目编辑。 |
| CO-B | [Coolors · #B09A21](https://coolors.co/b09a21) | 搜索索引可读取该黄铜色页及色彩和谐说明。夜航黄铜保留基色、另配自定暖银。 |

## 逐组冻结清单与黑底对比度

数值使用现有 `watchface/build.py::contrast_on_black` 计算，采用 sRGB 线性化和相对亮度权重 0.2126 / 0.7152 / 0.0722。两个颜色各自与黑色比较，门槛为 4.5；不是小时色与分钟色互比。表内显示值四舍五入到两位小数，判定使用未舍入值。

数据检查结果：两套均为 32 个唯一 ASCII 名称、32 对唯一有序配色、64 个合法大写 `#RRGGBB` 颜色；共 128 次颜色核验全部通过。Meridian 最低值仍为 `#A149FA` 的 **4.848856361361047:1**；修订后的 Ultra 最低值为 `#6085B2` 的 **5.4952413314216395:1**。

### Meridian

| 索引 | 名称 | 风格 | 小时 / 分钟 | 黑底对比度（小时 / 分钟） | 来源 |
| --- | --- | --- | --- | --- | --- |
| 1 | 鎏金明暗 / `burnished_gold` | metallic | `#EADCA6` / `#C49F45` | 15.29 / 8.39 | CH-M |
| 2 | 香槟金 / `champagne_gold` | metallic | `#F0E1BC` / `#BFA66A` | 16.20 / 8.88 | CH-B |
| 3 | 白金浅影 / `white_gold` | metallic | `#E8E3D1` / `#B6AC8B` | 16.34 / 9.26 | CH-B |
| 4 | 古铜黄铜 / `antique_brass` | metallic | `#D6C486` / `#A99C57` | 12.10 / 7.58 | CH-B |
| 5 | 赤铜微光 / `copper_sheen` | metallic | `#E3AA83` / `#B87C4C` | 10.34 / 6.03 | CH-B |
| 6 | 缎面青铜 / `bronze_satin` | metallic | `#D2AF80` / `#9D825A` | 10.18 / 5.77 | CH-B |
| 7 | 玫瑰金属 / `rose_gold` | metallic | `#E4BFA8` / `#B98575` | 12.32 / 6.67 | CH-B |
| 8 | 铂金冷辉 / `platinum_edge` | metallic | `#D8DDDE` / `#909CA3` | 15.32 / 7.47 | CH-S |
| 9 | 拉丝亮银 / `brushed_silver` | metallic | `#E6E9E9` / `#A6ADAF` | 17.20 / 9.22 | CH-D |
| 10 | 钛灰哑光 / `titanium_matte` | metallic | `#C3C8CD` / `#858D96` | 12.46 / 6.25 | CH-S |
| 11 | 枪灰银边 / `gunmetal_silver` | metallic | `#B3BEC8` / `#778793` | 11.12 / 5.67 | CH-D |
| 12 | 钢蓝冷光 / `steel_blue` | metallic | `#C7D9E5` / `#7194B0` | 14.48 / 6.57 | CH-S |
| 13 | 青钛合金 / `teal_titanium` | metallic | `#B9D6D2` / `#5D9D98` | 13.61 / 6.74 | CH-V |
| 14 | 绿铜淡金 / `patina_gold` | metallic | `#CBBF8D` / `#739F89` | 11.38 / 7.05 | CH-V |
| 15 | 钴蓝合金 / `cobalt_alloy` | metallic | `#A6C0D8` / `#638CBD` | 11.15 / 6.02 | CH-S |
| 16 | 紫钛微辉 / `violet_titanium` | metallic | `#C8BFDC` / `#9485B5` | 11.94 / 6.28 | CH-V |
| 17 | 泳池橘 / `pool_tangerine` | plastic | `#00D1FF` / `#FF9B32` | 11.56 / 9.99 | CH-W |
| 18 | 柑橘外壳 / `citrus_shell` | plastic | `#FF8400` / `#FFD93D` | 8.55 / 15.24 | CH-W |
| 19 | 水蓝外壳 / `aqua_shell` | plastic | `#00D1FF` / `#00FFF0` | 11.56 / 16.56 | CH-W |
| 20 | 紫柠拼色 / `violet_lemon` | plastic | `#A58BFF` / `#FFF46E` | 7.74 / 18.42 | CH-W |
| 21 | 珊瑚水青 / `coral_aqua` | plastic | `#FF5F5F` / `#83FFE6` | 7.05 / 17.41 | CH-W |
| 22 | 烈焰橙红 / `flame_orange` | plastic | `#F93827` / `#FF9D23` | 5.62 / 10.10 | CH-G |
| 23 | 柠檬翡翠 / `lemon_jade` | plastic | `#FFCC29` / `#00AF91` | 13.92 / 7.54 | CH-G |
| 24 | 橘色翡翠 / `orange_jade` | plastic | `#F58634` / `#00AF91` | 8.34 / 7.54 | CH-G |
| 25 | 天蓝青柠 / `azure_lime` | plastic | `#2192FF` / `#9CFF2E` | 6.62 / 16.76 | CH-G |
| 26 | 亮绿柠黄 / `green_lemon` | plastic | `#38E54D` / `#FDFF00` | 12.48 / 19.48 | CH-L |
| 27 | 泻湖亮蓝 / `lagoon_azure` | plastic | `#00FFDD` / `#2FA4FF` | 16.35 / 7.88 | CH-G |
| 28 | 葡萄电黄 / `grape_voltage` | plastic | `#A149FA` / `#F7EC09` | 4.85 / 16.96 | CH-G |
| 29 | 蜜橘薄荷 / `tangerine_mint` | plastic | `#FF9137` / `#70FFD2` | 9.36 / 16.92 | CH-L |
| 30 | 杏橘湖青 / `apricot_turquoise` | plastic | `#FFB76C` / `#26CCC2` | 12.24 / 10.50 | CH-L |
| 31 | 橙红拼壳 / `red_orange_shell` | plastic | `#FF5656` / `#FFA239` | 6.72 / 10.48 | CH-L |
| 32 | 天青薄荷 / `sky_mint_shell` | plastic | `#63C8FF` / `#4DFFBE` | 11.24 / 16.36 | CH-L |

### Ultra

本次仅修订 Ultra，Meridian 色库及上方逐组数据保持原样。24 组运动配色保留明快主色，辅色收敛为柔和同色系或中性色；8 组沉稳商务配色保留。蓝黄的黄色从荧光黄调整为麦金，其他强烈冷暖配对也已重新调和。

辅助检查：32 组全部满足“每组至多一个颜色的 HSV 饱和度达到 0.65”，且没有两色同时具有 255 的最大 RGB 通道。这两项只用于拦截双高饱和、双满亮配色，最终协调性仍由同色系关系、主辅层次和整表预览共同判断。表中 S 为 HSV 饱和度，非 HSL。

| 索引 | 名称 | 风格 | 小时 / 分钟 | 黑底对比度（小时 / 分钟） | S（小时 / 分钟） | 来源 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 蓝调麦金 / `blue_straw` | sport | `#6596C4` / `#D1BC73` | 6.71 / 11.15 | 0.485 / 0.450 | CH-G |
| 2 | 海蓝薄雾 / `azure_mist` | sport | `#3299D3` / `#A5C3D3` | 6.63 / 11.35 | 0.763 / 0.218 | CH-W |
| 3 | 拉力琥珀 / `rally_amber` | sport | `#EB9554` / `#C4B8A7` | 8.96 / 10.76 | 0.643 / 0.148 | CH-W |
| 4 | 跑道朱红 / `track_vermilion` | sport | `#E47158` / `#C4ACA3` | 6.80 / 9.78 | 0.614 / 0.168 | CH-L |
| 5 | 草地灰绿 / `grass_track` | sport | `#8AB942` / `#B7C2AC` | 9.10 / 11.33 | 0.643 / 0.113 | CH-G |
| 6 | 泻湖钢青 / `lagoon_steel` | sport | `#3CB59C` / `#A2BDB4` | 8.28 / 10.47 | 0.669 / 0.143 | CH-G |
| 7 | 杏橘沙地 / `apricot_field` | sport | `#DE9B60` / `#D0C0A6` | 8.96 / 11.77 | 0.568 / 0.202 | CH-G |
| 8 | 蓝紫钢色 / `violet_steel` | sport | `#9581CB` / `#ADB8CA` | 6.28 / 10.49 | 0.365 / 0.144 | CH-G |
| 9 | 涡轮蓝调 / `turbine_blue` | sport | `#458FD2` / `#A5B8CD` | 6.11 / 10.34 | 0.671 / 0.195 | CH-W |
| 10 | 松绿疾行 / `pine_sprint` | sport | `#43AC78` / `#A1B6A7` | 7.41 / 9.76 | 0.610 / 0.115 | CH-G |
| 11 | 冰川流线 / `arctic_current` | sport | `#59AFC8` / `#B4C9CC` | 8.39 / 12.17 | 0.555 / 0.118 | CH-L |
| 12 | 麦金沙色 / `ochre_sand` | sport | `#CFAB56` / `#BDB5A0` | 9.61 / 10.28 | 0.585 / 0.153 | CH-L |
| 13 | 竞速朱砂 / `racing_red` | sport | `#D96F55` / `#BFAEA2` | 6.36 / 9.79 | 0.608 / 0.152 | CH-G |
| 14 | 海岸蓝灰 / `coastal_sky` | sport | `#549FC1` / `#A4BCC4` | 7.11 / 10.57 | 0.565 / 0.163 | CH-G |
| 15 | 日落陶橘 / `sunset_clay` | sport | `#D99C65` / `#BFB1A6` | 8.89 / 10.05 | 0.535 / 0.131 | CH-G |
| 16 | 球场橄榄 / `court_olive` | sport | `#A0B850` / `#C0C5A6` | 9.47 / 11.78 | 0.565 / 0.157 | CH-G |
| 17 | 冲浪青灰 / `surf_sage` | sport | `#3EAE9C` / `#A9BEAD` | 7.74 / 10.66 | 0.644 / 0.111 | CH-G |
| 18 | 球场水青 / `stadium_aqua` | sport | `#5CB1AA` / `#B8C8C0` | 8.32 / 12.06 | 0.480 / 0.080 | CH-L |
| 19 | 流线青蓝 / `jet_cyan` | sport | `#28A6BB` / `#A6BAC0` | 7.26 / 10.41 | 0.786 / 0.135 | CO-C |
| 20 | 耐力青金 / `endurance_teal` | sport | `#4FB2A8` / `#C9BE93` | 8.27 / 11.27 | 0.556 / 0.269 | CO-A + CO-G |
| 21 | 山径铜橘 / `trail_copper` | sport | `#D58F58` / `#BDB7A6` | 7.90 / 10.49 | 0.587 / 0.122 | CH-G |
| 22 | 疾风天蓝 / `velocity_sky` | sport | `#60AAD4` / `#BBCBD1` | 8.20 / 12.58 | 0.547 / 0.105 | CH-L |
| 23 | 赛场麦金 / `pitlane_straw` | sport | `#C9AE62` / `#A8B5BF` | 9.71 / 10.03 | 0.512 / 0.120 | CH-G |
| 24 | 山野蕨绿 / `highland_fern` | sport | `#65B17E` / `#C1C5A8` | 8.14 / 11.82 | 0.429 / 0.147 | CH-G |
| 25 | 海军钢蓝 / `navy_steel` | business | `#6085B2` / `#D1D9E4` | 5.50 / 14.76 | 0.461 / 0.083 | CH-D |
| 26 | 碳灰琥珀 / `carbon_amber` | business | `#B0B8BE` / `#D89216` | 10.45 / 8.04 | 0.074 / 0.898 | CH-V |
| 27 | 森林黄铜 / `forest_brass` | business | `#8BAE66` / `#EBD5AB` | 8.34 / 14.64 | 0.414 / 0.272 | CH-V |
| 28 | 石油钢青 / `steel_petrol` | business | `#7A9EA3` / `#D3DAD9` | 7.25 / 14.80 | 0.252 / 0.032 | CH-V |
| 29 | 石墨赤铜 / `graphite_copper` | business | `#B6BCC3` / `#C99773` | 10.97 / 8.16 | 0.067 / 0.428 | CH-V |
| 30 | 板岩银沙 / `slate_sand` | business | `#9DB2BF` / `#DDE6ED` | 9.55 / 16.62 | 0.178 / 0.068 | CH-D |
| 31 | 夜航黄铜 / `brass_night` | business | `#B09A21` / `#D5D4C7` | 7.49 / 14.07 | 0.812 / 0.066 | CO-B |
| 32 | 蓝钢计时 / `blue_chronometer` | business | `#748DA6` / `#C3CED8` | 6.10 / 13.14 | 0.301 / 0.097 | CH-S |

## 本文覆盖范围

本清单核验色库数据和静态黑底对比度。本文仅冻结选色依据；Signal/Meridian 的原布局保留，Ultra 的 LED 信息板与底部指标更新另见 [0.1.19](../releases/0.1.19/README.md)。三款仍使用既有时段选择器。资源构建、Lua 精度回归、整表渲染及设备验收由该发布记录统一列明，本清单不把颜色数据核验当作真机显示验收。
