# macOS 血糖镜像

状态栏沿用[0.4.6样式](../releases/cloud-0.4.6/README.md)的淡色折线图标与仅图标着色的范围警示；简洁重点卡片和时间标记见[0.5.0](../releases/cloud-0.5.0/README.md)。

0.6.0为“动态24h”和“每日回顾”各加入“详细解读”入口，打开独立、可缩放的报告窗口。打开或查询只使用GET；首次需要主动点击“生成详细解读”，已有结果直接展示。解读固定对应选中的简报时段和reportId，主页面与组件保持简洁；详细窗口按关键解读、原因假设（支持/其他解释/验证办法）、可执行调整和对应文献组织。简报更新时保留所选时段，提示其已是历史解读，不自动切换或调用模型。

详细请求为`POST /api/v1/analysis/detail`，JSON只含`kind`与`reportId`，使用分析能力；GET同路径带查询参数使用只读能力。它与简报原有的零字节POST不同。窗口仅在生成中短时查询，关闭立即停止；未知提交结果只查询，不自动再POST。连接更改、报告ID不匹配的回包不会显示。缓存时限由服务端决定（动态最长8h、每日最长24h）；过期或资料有修正时保留旧解读，只有用户主动点击才生成新版。

0.3.0新增“动态24h／每日回顾”分段切换，共用一个报告文本区。动态分析按钮在最近24h资料就绪且拥有分析权限时可用，至少间隔30min，同一快照复用；固定日报覆盖前一自然日并独立保留。刷新改为无背景图标（点击轻转一圈）；左下“设置…”打开真正独立窗口，主页不再嵌入连接/启动设置。

原生 SwiftUI 菜单栏应用与 WidgetKit 通知中心组件，最低 macOS 15。0.2.10 修复了真实小组件空白：此前扩展能找到 App Group，但系统拒绝读取快照（`permission_denied`），CFPreferences 也没有得到数据。现在组件在自己的沙盒内，以独立只读连接通过 HTTPS 读取 Ali，并保存自己的 0600 缓存；不再依赖主应用的共享文件。保留 sandbox，仅增加标准 `network.client` 权限，没有关闭证书校验或绕过文件保护。

菜单栏将应用风格的淡色折线图标与完整Helvetica Neue Regular 14pt数字合成为一张图，高16.2pt；透明隔离边让后方图案避开数字。3.9–7.8（含端点）保持单色模板图，新鲜读数低于3.9时仅图标红色、高于7.8时仅图标橙色；数字始终采用黑白前景，缺失/过期读数淡化且不继续范围警示。彩色图在drawingHandler内按当前绘制外观解析数字颜色，并禁用首次外观缓存。提示文字/可访问标签复用同一范围状态。菜单栏不显示趋势箭头，详情和组件保留趋势。合成单图避免系统把Image/Text重新分开排版。单实例保护使用当前用户私密目录内的原子 `flock`，兼容识别升级前进程。重复启动转交详情请求后退出；安装时退出旧实例、移除构建副本登记，只登记已安装应用。点击小组件通过 AppKit 打开详情窗口。

主应用每五分钟读取同一 `/api/v1/dashboard`，更新菜单栏并请求 WidgetKit 重载。组件自己的 TimelineProvider 异步获取数据，即使主应用退出仍有独立获取路径。系统决定实际刷新预算，不能保证严格五分钟到达；组件保留测量时刻，并在读数超过十分钟后灰显，不将缓存当成新读数。网络失败保留最近快照。参考 Apple 的 [网络请求说明](https://developer.apple.com/documentation/widgetkit/making-network-requests-in-a-widget-extension) 和 [刷新机制](https://developer.apple.com/documentation/widgetkit/keeping-a-widget-up-to-date)。

详情与组件使用浅彩渐变及白色信息卡，时间为 24 小时 `HH:mm`。包含过去 24h 曲线、3.9/7.8 观察参考线、历史同时段中位数、区间占比、均值、极值、覆盖率及每日分析。3.9–7.8 是观察区间，不是诊断目标。缺测超过十分钟断线；历史灰线要求至少三个不同历史日，各日内桶也至少来自三日。报告显示日期、失败/旧报告状态。

## 构建、测试与安装

```sh
sh macos/test.sh
sh macos/build.sh
sh macos/install.sh --import-config /absolute/private-config.json
```

仅依赖完整 Xcode、Swift、Python 3 和系统工具。工程由 `generate_project.py` 确定性生成。产物在 `macos/build/Build/Products/Release/OttaiMirror.app`，包含真正的扩展。默认逐层 ad-hoc 签名供本机运行；可通过 `OTTAI_SIGN_IDENTITY` 和 Xcode 构建参数指定个人签名，证书/profile 不进 Git。个人构建没有 notarization，跨机器安装时仍需按系统正常流程授权。

输入文件须当前用户所有、0600、非符号链接，格式如下（只有占位）：

```json
{"baseURL":"https://your-service.example/ottai","readToken":"YOUR_READ_ONLY_TOKEN","analysisToken":"OPTIONAL_SEPARATE_ANALYSIS_CAPABILITY_32_PLUS_CHARS"}
```

安装脚本先校验并原子写入主应用与组件的独立配置，再覆盖 `~/Applications/OttaiMirror.app`，写入 `~/Library/LaunchAgents/com.joviliu.ottai.mirror.plist`，供用户下一次登录后启动。不会把令牌写入 LaunchAgent、命令行或应用包。已配置机器可直接执行 `sh macos/install.sh`，沿用主应用配置并同步组件。仅 GUI 修改连接不会替另一沙盒写设置，更换凭据后须重跑该命令。

通知中心 → 编辑小组件 → 搜索“血糖镜像” → 添加中号/大号。已添加组件覆盖升级后通常无需重加。设置由左下“设置…”打开独立AppKit窗口。分析权限只保存在主应用，安装脚本明确剥除后才给Widget配置，只读组件不能发起模型分析。

## 凭据与缓存

刷新完全不调用 Security/SecItem，不会读旧钥匙串条目。旧条目可保留。只读配置启动时读入内存；文件与父目录分别要求 0600/0700，拒绝错误所有者、链接和超限文件。只接受 HTTPS，禁止重定向，组件请求限时 15 秒、响应最多 2 MB，不密集重试。

- 主应用：`~/Library/Application Support/OttaiMirror/connection.json` 和 `dashboard.json`。
- 组件：`~/Library/Containers/com.joviliu.ottai.mirror.widget/Data/Library/Application Support/OttaiMirror/connection.json` 和 `widget-dashboard.json`。

上述文件是私密配置或健康资料，不提交仓库。只读令牌不能上传或调用模型。导入完成可删除传递用的临时 JSON。

## 验证与诊断

`macos/test.sh` 验证数据格式、过期/缺测、跨进程锁、私密配置、缓存，以及组件 HTTPS 路径/鉴权、断网缓存、401、重定向拒绝、超限响应、错误 JSON、宽权限和链接拒绝；详细解读另验证GET打开/轮询不触发POST、显式JSON与权限、两类报告ID绑定、修正后主动更新、未知结果不重复提交、关闭/连接变化和文献/正文边界。同时生成明确标为合成数据的原生 View 预览，含`report-events-synthetic-detail.png`。预览不代替通知中心或真实报告窗口验收。

运行时日志只记录阶段、固定错误类别和源条数，不含血糖值、测量时刻、令牌或原始错误：

```sh
log show --last 10m --style compact --predicate 'subsystem == "com.joviliu.ottai.mirror.widget" AND category == "widget-cache"'
```

`phase=timeline transport=https category=ok sourceCount>0` 表示真正的系统 Provider 已获取正式资料。仍需确认通知中心实际显示与后续新测量刷新；完整验收状态见 [接续记录](../docs/CLOUD_SYNC_HANDOFF.md)。长期离线恢复、系统刷新预算和跨机器签名未用短时本机验证代替。
