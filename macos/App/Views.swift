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
                    GlucoseChart(dashboard: dashboard, compact: compact, eventEditor: { selected in
                        AnyView(EventEditor(model: model, selection: selected))
                    }).frame(height: dashboard.activity == nil ? (compact ? 170 : 240) : (compact ? 310 : 400))
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
    @State private var expandedSummary = false
    private var report: Analysis? {
        let data = model.snapshot?.dashboard
        if selection == "rolling" { return data?.rollingAnalysis }
        return data?.dailyAnalysis ?? (data?.analysis?.trigger?.hasPrefix("manual") == true ? nil : data?.analysis)
    }
    private var detailSelection: DetailReportSelection? {
        guard let report, report.generatedAt != nil, let id = report.reportId, validReportID(id) else { return nil }
        return DetailReportSelection(kind: selection, reportId: id, periodStart: report.periodStart, periodEnd: report.periodEnd)
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label("血糖观察", systemImage: "sparkle").font(.headline).foregroundStyle(MirrorPalette.violet)
                Spacer()
                Text(report?.displayStatus ?? "等待数据").font(.caption).foregroundStyle(MirrorPalette.muted)
            }
            Picker("分析类型", selection: $selection) {
                Text("动态24h").tag("rolling")
                Text("每日回顾").tag("daily")
            }.pickerStyle(.segmented)
            if selection == "rolling" {
                Button { Task { await model.analyzeRecent() } } label: {
                    Label(model.analyzing ? "正在分析…" : "分析过去24小时", systemImage: "sparkles")
                }.disabled(!model.canAnalyze).buttonStyle(.borderedProminent).tint(MirrorPalette.violet).controlSize(.small)
                if !model.analysisMessage.isEmpty || !model.canAnalyze {
                    Text(model.analysisMessage.isEmpty ? model.analysisReason : model.analysisMessage)
                        .font(.caption).foregroundStyle(MirrorPalette.muted)
                }
            }
            if let report {
                if let period = report.periodDescription { Text(period).font(.caption).monospacedDigit().foregroundStyle(MirrorPalette.muted) }
                if report.dataStale == true { Label("生成后有新记录", systemImage: "arrow.triangle.2.circlepath").font(.caption).foregroundStyle(MirrorPalette.muted) }
                if let summary = report.summary, !summary.isEmpty {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(reportInlineText(summary)).font(.callout.weight(.medium)).textSelection(.enabled)
                            .lineLimit(expandedSummary ? nil : 4)
                        if summary.count > 140 { Button(expandedSummary ? "收起" : "展开结论") { expandedSummary.toggle() }.font(.caption).buttonStyle(.plain).foregroundStyle(MirrorPalette.blue) }
                    }
                }
                if let highlights = report.highlights, !highlights.isEmpty {
                    ForEach(Array(highlights.prefix(3))) { highlight in HighlightCard(highlight: highlight) }
                } else if !(report.sections ?? []).isEmpty {
                    DisclosureGroup("查看原报告") {
                        VStack(alignment: .leading, spacing: 10) {
                            ForEach(report.sections ?? []) { section in
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(section.title).font(.subheadline.weight(.semibold))
                                    Text(reportInlineText(section.text)).font(.callout).textSelection(.enabled)
                                }
                            }
                        }.padding(.top, 7)
                    }.font(.caption).tint(MirrorPalette.muted)
                }
                if !(report.evidence ?? []).isEmpty || !(report.sources ?? []).isEmpty || !(report.limitations ?? []).isEmpty {
                    DisclosureGroup("依据与补充") {
                        VStack(alignment: .leading, spacing: 9) {
                            ForEach(report.evidence ?? []) { item in
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(item.title).font(.caption.weight(.semibold))
                                    Text(reportInlineText(item.text)).font(.caption).textSelection(.enabled)
                                    if let url = URL(string: item.sourceUrl), url.scheme == "https" { Link("查看来源", destination: url).font(.caption2) }
                                }
                            }
                            if (report.evidence ?? []).isEmpty {
                                ForEach(report.sources ?? []) { source in
                                    if let url = URL(string: source.url), url.scheme == "https" { Link(source.title, destination: url).font(.caption) }
                                }
                            }
                            ForEach(report.limitations ?? [], id: \.self) { Text($0).font(.caption2).foregroundStyle(MirrorPalette.muted) }
                        }.padding(.top, 7)
                    }.font(.caption).tint(MirrorPalette.muted)
                }
            } else {
                Text(selection == "rolling" ? "最近24小时数据就绪后，可生成动态分析。" : "自动回顾会在每日生成。")
                    .font(.callout).foregroundStyle(MirrorPalette.muted)
            }
            Button {
                if let detailSelection { NotificationCenter.default.post(name: AppNavigation.detail, object: detailSelection) }
            } label: { Label("详细解读", systemImage: "text.magnifyingglass") }
                .buttonStyle(.bordered).tint(MirrorPalette.blue).controlSize(.small)
                .disabled(detailSelection == nil).help("对当前所选报告时段生成或查看详细解读")
            if detailSelection == nil {
                Text("这类报告就绪后可查看详细解读。").font(.caption).foregroundStyle(MirrorPalette.muted)
            }
        }.frame(maxWidth: .infinity, alignment: .leading).mirrorCard(padding: compact ? 14 : 20)
    }
}

private struct HighlightCard: View {
    let highlight: AnalysisHighlight
    var body: some View {
        HStack(alignment: .top, spacing: 9) {
            Image(systemName: highlight.symbol).foregroundStyle(highlight.tint).font(.system(size: 14)).padding(.top, 1)
            VStack(alignment: .leading, spacing: 5) {
                Text(highlight.title).font(.subheadline.weight(.bold)).foregroundStyle(highlight.tint)
                Text(reportInlineText(highlight.text)).font(.callout).textSelection(.enabled)
                if let action = highlight.action, !action.isEmpty {
                    Text(reportInlineText(action)).font(.callout.weight(.medium)).foregroundStyle(highlight.tint)
                }
            }
        }.padding(12).frame(maxWidth: .infinity, alignment: .leading)
            .background(highlight.tint.opacity(0.075), in: RoundedRectangle(cornerRadius: 12))
    }
}

func reportInlineText(_ text: String) -> AttributedString {
    var result = (try? AttributedString(markdown: text, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(text)
    for run in result.runs where run.link != nil { result[run.range].link = nil }
    return result
}

struct EventEditor: View {
    @ObservedObject var model: AppModel
    @Environment(\.dismiss) private var dismiss
    private let existing: LifestyleEvent?
    @State private var eventID: String
    @State private var connectionAtOpen: String
    @State private var kind: LifestyleEventKind
    @State private var time: Date
    @State private var note: String
    @State private var foods: String
    @State private var error = ""
    @State private var confirmingDelete = false

    init(model: AppModel, selection: ChartEventSelection) {
        self.model = model
        existing = selection.event
        _eventID = State(initialValue: selection.event?.id ?? UUID().uuidString)
        _connectionAtOpen = State(initialValue: model.baseURL)
        _kind = State(initialValue: selection.event?.type ?? .meal)
        _time = State(initialValue: selection.event?.date ?? ChartSelection.minuteDate(selection.date))
        _note = State(initialValue: selection.event?.note ?? "")
        _foods = State(initialValue: selection.event?.meal?.foods ?? "")
    }
    private var fieldsValid: Bool { note.unicodeScalars.count <= 1000 && (kind != .meal || foods.unicodeScalars.count <= 1000) }
    var body: some View {
        VStack(alignment: .leading, spacing: 13) {
            HStack {
                Text(existing == nil ? "记录这一刻" : "编辑记录").font(.headline)
                Spacer()
                Button { dismiss() } label: { Image(systemName: "xmark").font(.system(size: 10, weight: .semibold)) }
                    .buttonStyle(.plain).foregroundStyle(MirrorPalette.muted).accessibilityLabel("关闭记录编辑")
            }
            VStack(alignment: .leading, spacing: 5) {
                Text("大约时间").font(.caption).foregroundStyle(MirrorPalette.muted)
                DatePicker("大约时间", selection: $time, in: Date().addingTimeInterval(-365 * 86400)...Date().addingTimeInterval(300), displayedComponents: [.date, .hourAndMinute])
                    .labelsHidden().datePickerStyle(.field).environment(\.locale, Locale(identifier: "zh_CN"))
            }
            LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 3), spacing: 7) {
                ForEach(LifestyleEventKind.allCases) { item in
                    Button { kind = item } label: {
                        Label(item.title, systemImage: item.symbol).font(.system(size: 12, weight: .medium))
                            .frame(maxWidth: .infinity).padding(.vertical, 8)
                            .foregroundStyle(kind == item ? item.tint : MirrorPalette.muted)
                            .background((kind == item ? item.tint.opacity(0.12) : Color.gray.opacity(0.04)), in: RoundedRectangle(cornerRadius: 8))
                    }.buttonStyle(.plain)
                }
            }
            if kind == .meal {
                TextField("吃了什么（可选）", text: $foods, axis: .vertical).lineLimit(1...3).textFieldStyle(.roundedBorder)
                if let meal = existing?.meal, foods == meal.foods, let low = meal.estimatedKcalMin, let high = meal.estimatedKcalMax {
                    Text("约 \(metricText(low, decimals: 0))–\(metricText(high, decimals: 0)) kcal").font(.caption).foregroundStyle(MirrorPalette.muted)
                }
            }
            TextField("补充内容（可选）", text: $note, axis: .vertical).lineLimit(1...3).textFieldStyle(.roundedBorder)
            if !model.canEditEvents { Text("当前为只读连接，请在设置中导入分析权限后记录。").font(.caption).foregroundStyle(MirrorPalette.muted) }
            if !fieldsValid { Text("每项最多1000字。").font(.caption).foregroundStyle(.red) }
            if !error.isEmpty { Text(error).font(.caption).foregroundStyle(.red).fixedSize(horizontal: false, vertical: true) }
            HStack {
                if existing != nil {
                    Button("删除记录", role: .destructive) { confirmingDelete = true }.buttonStyle(.borderless)
                        .disabled(model.eventSaving || !model.canEditEvents)
                }
                Spacer()
                Button(model.eventSaving ? "保存中…" : "保存记录") { Task { await save() } }
                    .buttonStyle(.borderedProminent).tint(kind.tint)
                    .disabled(model.eventSaving || !model.canEditEvents || !fieldsValid)
            }
        }.padding(18).frame(width: 320).foregroundStyle(MirrorPalette.ink).background(Color.white)
            .preferredColorScheme(.light)
            .alert("删除这条记录？", isPresented: $confirmingDelete) {
                Button("取消", role: .cancel) {}
                Button("删除", role: .destructive) { Task { await remove() } }
            }
    }
    private func save() async {
        guard model.baseURL == connectionAtOpen else { error = "连接已更改，请重新打开记录。"; return }
        let meal = kind == .meal ? MealDetails.recording(foods: foods, previous: existing?.meal) : nil
        let event = LifestyleEvent(id: eventID, type: kind, at: ChartSelection.minuteDate(time).timeIntervalSince1970 * 1000,
                                   note: note.trimmingCharacters(in: .whitespacesAndNewlines), meal: meal, updatedAt: existing?.updatedAt)
        do { try await model.saveEvent(event); dismiss() }
        catch { self.error = error.localizedDescription }
    }
    private func remove() async {
        guard model.baseURL == connectionAtOpen, let existing else { error = "连接已更改，请重新打开记录。"; return }
        do { try await model.deleteEvent(existing); dismiss() }
        catch { self.error = error.localizedDescription }
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
