# Signal 0.1.17：Poiret One 原字形

2026-10-29。本次只覆盖 Signal `8670260102`；Ultra 保持已装 0.1.14，Meridian 保持已确认的 0.1.16。手机 APK 0.1.11 和手表 RPK 0.1.12 不升级。

- 时间/血糖改用用户指定的 Poiret One 原字体，等比缩放，保留圆润数字与细线条，不纵向拉长、不加球衣描边。
- 原日期、大时钟区域、48px 血糖信息行、更新时间、电量和心率的位置保留；横排四位按原字体比例适配，实际字形高度较球衣版降低。
- 时钟继续使用 32 组预着色图片，04/11/15/19 稳定换组；没有恢复未生效的 image recolor。
- 血糖正常值保留柔和浅紫，偏高/其他有效值仍按原阈值黄/红；旧数据仍变暗并显示原始时间及 OLD。

BIN 为 2,651,440 字节、767 个资源。先核对 SHA256SUMS。预览均为合成值，不是个人医疗数据或屏摄。

## 已验证

已完成本地 UI/数据/全日资源/全部 32 组可达/实际像素色和字形边界检查，并增加圆形 0 的比例断言。真机上传 INSTALL_OK；用户已确认 Signal 现在符合预期。原监听、两端默认启用与 FGS、两项后台豁免已复核；恢复后收到文件导出，临时安装器已卸载并确认不存在。

APK/RPK 本轮在非充电锁屏下完成两轮严格新测量自动写入/ACK，见 [验收记录](../../docs/validation.md)；该阶段为 0.1.15 Meridian，不能代作本版多日或实际跨时点耐久观察。32 组与时间边界的选择已经代码验证，本次真机确认了当前时段的配色和新字体。

## 字体与重建

Poiret One 原字体来自 [Google Fonts 固定提交](https://github.com/google/fonts/tree/8b0a1d0f5983c89bc2b93f1b5fb55f9e252744b5/ofl/poiretone)，文件未修改，SHA-256 `457f2d03263f58e5a6dbcc1b607b10dff6581e7cf9c4ebdf330ec3e6772a3558`。SIL OFL 完整文本见 [OFL-PoiretOne.txt](../../watchface/fonts/OFL-PoiretOne.txt)。只在构建时生成 PNG，手表不需安装 TTF。

```sh
python watchface/build.py --variant signal
python watchface/test_ui.py
# 验证三款资源前先构建 all，再运行：
python watchface/test_assets.py
```

新环境先读 [交接](../../docs/HANDOFF.md)，不要重复安装旧实验版，也不要把自己的配对凭据放入仓库。
