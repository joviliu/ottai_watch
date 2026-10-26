# 已撤回：透明窗口与延迟 UI 试验

本试验未通过实机自动更新验收，不用于当前源码或默认安装。

`implementation.patch` 是相对 Git 提交 `fda32d5` 的手表增量，新增测试另存为 `startup-ui.test.cjs`。复现时在独立的该提交检出上应用 patch，将测试放回 `watch/test/`，再执行 `npm ci`、`npm test` 与 `npm run release`。已构建包保存在 [watch-0.1.9](../../releases/watch-0.1.9/README.md)。

桌面逻辑测试和构建通过；手动启动先黑屏、两秒后主界面正常，透明没有显示下层表盘。两轮新测量都有手机通知和自动唤起请求，但没有文件导出回执；用户未观察到自动更新。失败原因未定位，不能断言是某一行门控导致。当前源码恢复 0.1.8 逻辑并递增为 0.1.10 / code 11。

公开平台接口没有给出已确认的无窗口 interconnect 服务；第二个 RPK 也没有已确认的无感优势。详见 [调研与证据](../../docs/silent-sync-research.md)。
