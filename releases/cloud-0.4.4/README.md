# Mac折线圆标与范围警示 0.4.4

2026-11-10。Mac/Widget build15。手机继续使用[0.4.3](../cloud-0.4.3/README.md)，服务端及手表不升级。

- 菜单栏采用应用风格的折线圆标。完整数字与图标半重叠，透明细边隔开后方图案，不再用XOR切割字形。
- 数字保持黑白；新鲜读数低于3.9时仅图标红色，高于7.8时仅图标橙色。3.9与7.8均属于黑白观察范围。旧值/缺失淡化，不作为当前范围警示。
- 数字在绘制时解析实际外观，警示图不缓存首次颜色。提示文字与可访问标签说明范围状态。既有图表、云连接、登录启动与单实例机制保留。

安装[Mac应用](OttaiMirror-0.4.4.zip)前核对[SHA256SUMS](SHA256SUMS)，优先按[安装脚本](../../macos/install.sh)覆盖同一路径，不保留重复注册副本。制品无连接配置、令牌或健康记录。

[合成菜单栏预览](menubar-synthetic.png)用于浅深外观、边界、缺失与警示检查，不是真实个人资料。完整Mac测试与Release构建/签名验证通过；边界、过期与仅图标着色有像素检查，同一图像浅→深→浅重绘不缓存首次数字颜色。实际选择高亮态未用合成背景冒充验收。

完整接续及实际验证边界见[云交接](../../docs/CLOUD_SYNC_HANDOFF.md)。

设计依据：[Apple菜单栏HIG](https://developer.apple.com/design/human-interface-guidelines/the-menu-bar)、[NSImage模板](https://developer.apple.com/documentation/appkit/nsimage/istemplate)、[动态绘制](https://developer.apple.com/documentation/appkit/nsimage/init(size:flipped:drawinghandler:))。混合彩图里的选中态文字没有自动反色保证，需实际核对；透明隔离边是本项目的实现选择。
