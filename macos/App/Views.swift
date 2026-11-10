import SwiftUI

struct MenuContent: View {
    @ObservedObject var model: AppModel
    var body: some View {
        VStack(spacing: 0) {
            DashboardView(model: model, compact: true)
            Divider()
            HStack {
                Button("设置…") { NotificationCenter.default.post(name: AppNavigation.settings, object: nil) }
                Spacer()
                Button("退出") { NSApplication.shared.terminate(nil) }
            }.buttonStyle(.borderless).foregroundStyle(MirrorPalette.blue).padding(12)
                .background(Color.white.opacity(0.8))
        }
        .background(MirrorPalette.background).preferredColorScheme(.light)
    }
}

struct DashboardView: View {
    @ObservedObject var model: AppModel
    var compact = false
    @State private var refreshRotation = 0.0
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: compact ? 12 : 18) {
                HStack(alignment: .firstTextBaseline) {
                    Text(model.latest?.display ?? "—").font(.system(size: compact ? 42 : 58, weight: .semibold, design: .rounded)).monospacedDigit()
                    Text(model.latest?.displayTrend ?? "→").font(.system(size: 30, weight: .medium))
                    Text("mmol/L").font(.callout).foregroundStyle(MirrorPalette.muted)
                    Spacer()
                    VStack(alignment: .trailing, spacing: 4) {
                        Text(model.stale ? "读数待更新" : "当前血糖").font(.caption.weight(.medium))
                        if let latest = model.latest { Text(DisplayTime.dateTime(latest.date)).font(.caption).monospacedDigit().foregroundStyle(MirrorPalette.muted) }
                    }
                }.foregroundStyle(model.stale ? Color.gray : MirrorPalette.blue)
                    .mirrorCard(padding: compact ? 14 : 20)
                if let dashboard = model.snapshot?.dashboard {
                    GlucoseChart(dashboard: dashboard, compact: compact).frame(height: dashboard.activity == nil ? (compact ? 134 : 210) : (compact ? 270 : 360))
                        .mirrorCard(padding: compact ? 12 : 20)
                    let metrics = dashboard.metrics
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible(), alignment: .leading), count: compact ? 2 : 4), spacing: compact ? 10 : 14) {
                        metric("区间占比", metricText(metrics?.inRangePercent, suffix: "%", decimals: 0), color: MirrorPalette.blue)
                        metric("平均血糖", metricText(metrics?.mean), color: MirrorPalette.violet)
                        metric("最高 / 最低", "\(metricText(metrics?.max)) / \(metricText(metrics?.min))", color: Color(red: 0.68, green: 0.43, blue: 0.29))
                        metric("数据覆盖", metricText(metrics?.coveragePercent, suffix: "%", decimals: 0), color: Color(red: 0.18, green: 0.55, blue: 0.49))
                    }
                    AnalysisPanel(model: model, compact: compact)

                } else {
                    ContentUnavailableView("等待首次同步", systemImage: "waveform.path.ecg", description: Text("在设置中连接服务后，手机上传的新读数会自动显示。"))
                        .mirrorCard()
                }
                if !model.message.isEmpty { Text(model.message).font(.caption).foregroundStyle(MirrorPalette.muted) }
                HStack {
                    if let fetched = model.snapshot?.fetchedAt { Text("获取于 \(DisplayTime.time(fetched))").font(.caption2).monospacedDigit() }
                    Spacer()
                    Button {
                        if !reduceMotion { refreshRotation += 360 }
                        Task { await model.refresh() }
                    } label: {
                        Image(systemName: "arrow.clockwise").font(.system(size: 13, weight: .semibold))
                            .rotationEffect(.degrees(refreshRotation))
                            .animation(.easeInOut(duration: 0.35), value: refreshRotation)
                            .padding(6).contentShape(Rectangle())
                    }.disabled(model.fetching).help("刷新数据").accessibilityLabel("刷新数据")
                        .buttonStyle(.plain).controlSize(.small)
                }.foregroundStyle(MirrorPalette.muted)
                if !compact {
                    Button("设置…") { NotificationCenter.default.post(name: AppNavigation.settings, object: nil) }.buttonStyle(.borderless)
                }
                Text("趋势观察不用于确诊、药量调整或替代医生诊疗。缺测区间不补造读数。").font(.caption2).foregroundStyle(MirrorPalette.muted)
            }.padding(compact ? 14 : 24)
        }.foregroundStyle(MirrorPalette.ink).background(MirrorPalette.background).preferredColorScheme(.light)
            .frame(width: compact ? 430 : 700, height: compact ? 650 : 800)
    }
    private func metric(_ title: String, _ value: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title).font(.caption).foregroundStyle(MirrorPalette.muted)
            Text(value).font(.system(size: compact ? 19 : 22, weight: .semibold, design: .rounded)).monospacedDigit().foregroundStyle(color)
        }.frame(maxWidth: .infinity, alignment: .leading).mirrorCard(padding: compact ? 11 : 16)
    }
}

struct AnalysisPanel: View {
    @ObservedObject var model: AppModel
    let compact: Bool
    @State private var selection = "rolling"
    private var report: Analysis? {
        let data = model.snapshot?.dashboard
        return selection == "rolling" ? data?.rollingAnalysis : data?.dailyAnalysis ?? data?.analysis
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("血糖分析", systemImage: "sparkle").font(.headline).foregroundStyle(MirrorPalette.violet)
                Spacer()
                Text(report?.displayStatus ?? "等待数据").font(.caption).foregroundStyle(MirrorPalette.muted)
            }
            Picker("分析类型", selection: $selection) {
                Text("动态24h").tag("rolling")
                Text("每日回顾").tag("daily")
            }.pickerStyle(.segmented)
            if selection == "rolling" {
                Button {
                    Task { await model.analyzeRecent() }
                } label: {
                    Label(model.analyzing ? "正在分析…" : "分析过去24小时", systemImage: "sparkles")
                }.disabled(!model.canAnalyze).buttonStyle(.borderedProminent).tint(MirrorPalette.violet).controlSize(.small)
                Text(model.analysisMessage.isEmpty ? model.analysisReason : model.analysisMessage).font(.caption).foregroundStyle(MirrorPalette.muted)
            }
            if let report {
                if let period = report.periodDescription { Text(period).font(.caption).monospacedDigit().foregroundStyle(MirrorPalette.muted) }
                if report.dataStale == true { Text("保留的历史报告，等待新数据分析。").font(.caption).foregroundStyle(MirrorPalette.muted) }
                if let summary = report.summary, !summary.isEmpty { Text(summary).font(.callout).textSelection(.enabled) }
                ForEach(report.sections ?? []) { section in
                    VStack(alignment: .leading, spacing: 5) {
                        Text(section.title).font(.subheadline.weight(.semibold))
                        Text(section.text).font(.callout).textSelection(.enabled)
                    }
                }
                ForEach(report.limitations ?? [], id: \.self) { Text($0).font(.caption).foregroundStyle(MirrorPalette.muted) }
                if !compact {
                    ForEach(report.sources ?? []) { source in
                        if let url = URL(string: source.url), url.scheme == "https" { Link(source.title, destination: url).font(.caption) }
                    }
                }
            } else {
                Text(selection == "rolling" ? "最近24小时数据就绪后，可生成动态分析。" : "自动日报在积累超过72小时后生成，覆盖前一自然日。").font(.callout).foregroundStyle(MirrorPalette.muted)
            }
        }.frame(maxWidth: .infinity, alignment: .leading).mirrorCard(padding: compact ? 14 : 20)
    }
}

struct SettingsView: View {
    @ObservedObject var model: AppModel
    @State private var url = ""
    @State private var token = ""
    @State private var analysisToken = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            TextField("HTTPS 服务地址", text: $url).textFieldStyle(.roundedBorder)
            SecureField("只读令牌（留空保留原令牌）", text: $token).textFieldStyle(.roundedBorder)
            SecureField("手动分析权限（留空保留）", text: $analysisToken).textFieldStyle(.roundedBorder)
            HStack {
                Button("保存并连接") { Task { await model.configure(url: url, token: token.isEmpty ? nil : token, analysisToken: analysisToken.isEmpty ? nil : analysisToken); token = ""; analysisToken = "" } }
                Button("导入私密配置…") { Task { await model.importConfiguration(); url = model.baseURL } }
            }
            Toggle("登录后在菜单栏运行", isOn: Binding(get: { model.launchAtLogin }, set: { model.setStartup($0) }))
            Text("每 5 分钟获取一次。只读令牌保存在当前用户的私密配置文件中，并在进程内缓存；刷新不访问钥匙串。小组件使用独立的只读连接。")
                .font(.caption).foregroundStyle(.secondary)
            Text("更换连接后，请重新运行安装脚本以同步小组件连接设置。")
                .font(.caption).foregroundStyle(.secondary)
            if !model.message.isEmpty { Text(model.message).font(.caption) }
        }.frame(maxWidth: .infinity, alignment: .leading).preferredColorScheme(.light).onAppear { url = model.baseURL }
    }
}
