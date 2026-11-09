# macOS 血糖镜像

原生 SwiftUI 菜单栏应用与 WidgetKit 通知中心组件，最低 macOS 15。0.2.6 修复了真实小组件空白：此前扩展能找到 App Group，但系统拒绝读取快照（`permission_denied`），CFPreferences 也没有得到数据。现在组件在自己的沙盒内，以独立只读连接通过 HTTPS 读取 Ali，并保存自己的 0600 缓存；不再依赖主应用的共享文件。保留 sandbox，仅增加标准 `network.client` 权限，没有关闭证书校验或绕过文件保护。

菜单栏使用 Avenir Next Medium 数字和约 50% 重叠的浅色血滴，去掉菜单栏趋势箭头；详情和组件仍有趋势。单实例保护使用当前用户私密目录内的原子 `flock`，兼容识别升级前进程。重复启动转交详情请求后退出；安装时退出旧实例、移除构建副本登记，只登记已安装应用。点击小组件通过 AppKit 打开详情窗口。

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
{"baseURL":"https://your-service.example/ottai","readToken":"YOUR_READ_ONLY_TOKEN"}
```

安装脚本先校验并原子写入主应用与组件的独立配置，再覆盖 `~/Applications/OttaiMirror.app`，写入 `~/Library/LaunchAgents/com.joviliu.ottai.mirror.plist`，供用户下一次登录后启动。不会把令牌写入 LaunchAgent、命令行或应用包。已配置机器可直接执行 `sh macos/install.sh`，沿用主应用配置并同步组件。仅 GUI 修改连接不会替另一沙盒写设置，更换凭据后须重跑该命令。

通知中心 → 编辑小组件 → 搜索“血糖镜像” → 添加中号/大号。已添加组件覆盖升级后通常无需重加。设置在页面底部展开，“打开详情/设置”旧按钮已移除。

## 凭据与缓存

刷新完全不调用 Security/SecItem，不会读旧钥匙串条目。旧条目可保留。只读配置启动时读入内存；文件与父目录分别要求 0600/0700，拒绝错误所有者、链接和超限文件。只接受 HTTPS，禁止重定向，组件请求限时 15 秒、响应最多 2 MB，不密集重试。

- 主应用：`~/Library/Application Support/OttaiMirror/connection.json` 和 `dashboard.json`。
- 组件：`~/Library/Containers/com.joviliu.ottai.mirror.widget/Data/Library/Application Support/OttaiMirror/connection.json` 和 `widget-dashboard.json`。

上述文件是私密配置或健康资料，不提交仓库。只读令牌不能上传或调用模型。导入完成可删除传递用的临时 JSON。

## 验证与诊断

`macos/test.sh` 验证数据格式、过期/缺测、跨进程锁、私密配置、缓存，以及组件 HTTPS 路径/鉴权、断网缓存、401、重定向拒绝、超限响应、错误 JSON、宽权限和链接拒绝；同时生成明确标为合成数据的原生 View 预览。预览不代替通知中心实显。

运行时日志只记录阶段、固定错误类别和源条数，不含血糖值、测量时刻、令牌或原始错误：

```sh
log show --last 10m --style compact --predicate 'subsystem == "com.joviliu.ottai.mirror.widget" AND category == "widget-cache"'
```

`phase=timeline transport=https category=ok sourceCount>0` 表示真正的系统 Provider 已获取正式资料。仍需确认通知中心实际显示与后续新测量刷新；完整验收状态见 [接续记录](../docs/CLOUD_SYNC_HANDOFF.md)。长期离线恢复、系统刷新预算和跨机器签名未用短时本机验证代替。
