# 表盘 0.1.14：开发候选（待统一真机调试）

2026-10-29。手机镜像 0.1.11、RPK 0.1.10、官方小米运动健康 3.59.2 均无需升级或替换。本轮在 0.1.13 三款基础上将 Ultra 配色扩至 32 组，不改布局/时点；临时安装器仍用 0.1.5。上一轮已确认表盘为 0.1.12，以下制品尚无成功上传记录。

| 款式 | ID | BIN 字节 | 资源数 |
| --- | --- | --- | --- |
| Ottai Ultra | `8670260101` | 5,451,580 | 766 |
| Ottai Signal | `8670260102` | 1,196,032 | 147 |
| Ottai Meridian | `8670260103` | 3,451,132 | 907 |

- Ultra：保持原点阵布局，04/11/15/19 分时稳定随机选取 32 组协调双色（保留已认可的原 8 组，新增 24 组）；日期与血糖更新时间同为灰色。
- Signal：实心大数字、青瓷强调色、血糖卡片和指标行。
- Meridian：传统简洁刻度与暖象牙/灰青指针，每分钟更新时分针，无秒针；实心血糖数字。
- 三款共用原 RPK 的文件、校验与过期规则；保持用户指定紫/黄/红阈值，旧数据有 OLD。
- 缩略图采用占位；预览图均为合成示例，不是个人数据或真机截图。

## 本地验证

Lua 帧和三款 UI 测试、04/11/15/19 边界/午夜/跨年/闰日/夏令时/重载、数据与过期回归通过；全天每分钟引用资源存在、图形边界、BIN 打包解包、全部资源的 16 位入口检查通过。镜像 Java/JS 现有测试通过。临时安装器 0.1.5 已签名打包，三 ID 白名单、错误 ID/尺寸、解析与输出脱敏测试通过。

## 最后统一真机调试

Ultra 已有同 ID，用 replace；Signal/Meridian 首次用 install，不删除其他表盘。使用本项目本地 SPP 安装器和现有合法配对凭据，可保留官方运动健康，安装结束恢复原监听/后台同步并卸载临时安装器。见 [流程](../../tools/spp-installer/README.md)。

三款并存、实际字体/图形加载、真实数据文件读取、切换后的最新值及自然周期更新尚未验证；不能将本地测试或旧版验收写成新版本通过。配色边界已经桌面测试，尚未等待实机四个时点。

## 重建

```sh
python watchface/build.py --variant all
python watchface/test_frame.py
python watchface/test_ui.py
python watchface/test_assets.py
# 临时安装器沿用 Android 工具链和原签名：
python tools/spp-installer/build.py --face watchface/build/meridian/ottai-meridian-watch6.bin
```

详情见 [表盘工程](../../watchface/README.md) 与 [配色依据](../../docs/clock-palettes.md)。先核对本目录 SHA256SUMS；安装器及三款 BIN/ZIP 不包含密钥或运行时健康数据。
