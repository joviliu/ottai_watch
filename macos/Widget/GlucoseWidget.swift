import SwiftUI
import WidgetKit
import OSLog

private enum WidgetDiagnostics {
    static let logger = Logger(subsystem: "com.joviliu.ottai.mirror.widget", category: "widget-cache")
    static func record(_ result: WidgetRemoteResult, phase: String) {
        logger.notice("phase=\(phase, privacy: .public) transport=https category=\(result.category.rawValue, privacy: .public) sourceCount=\(result.snapshot?.dashboard.readings.count ?? 0, privacy: .public)")
    }
}

struct GlucoseEntry: TimelineEntry {
    let date: Date
    let snapshot: CachedDashboard?
}

struct GlucoseProvider: TimelineProvider {
    func placeholder(in context: Context) -> GlucoseEntry {
        return GlucoseEntry(date: Date(), snapshot: nil)
    }
    func getSnapshot(in context: Context, completion: @escaping (GlucoseEntry) -> Void) {
        RemoteDashboard().load { result in
            WidgetDiagnostics.record(result, phase: "snapshot")
            completion(GlucoseEntry(date: Date(), snapshot: result.snapshot))
        }
    }
    func getTimeline(in context: Context, completion: @escaping (Timeline<GlucoseEntry>) -> Void) {
        RemoteDashboard().load { result in
            WidgetDiagnostics.record(result, phase: "timeline")
            let snapshot = result.snapshot
            let now = Date()
            var entries = [GlucoseEntry(date: now, snapshot: snapshot)]
            if let source = snapshot?.dashboard.latest?.date {
                let staleAt = source.addingTimeInterval(601)
                if staleAt > now { entries.append(GlucoseEntry(date: staleAt, snapshot: snapshot)) }
            }
            completion(Timeline(entries: entries, policy: .after(now.addingTimeInterval(300))))
        }
    }
}

struct GlucoseWidgetView: View {
    let entry: GlucoseEntry
    var familyOverride: WidgetFamily? = nil
    @Environment(\.widgetFamily) private var environmentFamily
    var family: WidgetFamily { familyOverride ?? environmentFamily }
    var stale: Bool { entry.snapshot?.dashboard.latest?.isStale(at: entry.date) ?? true }
    var reportSummary: String {
        let analysis = entry.snapshot?.dashboard.analysis
        if let summary = analysis?.summary, !summary.isEmpty { return summary }
        if analysis?.status == "error" || analysis?.status == "failed" { return "本次分析暂未生成，原始曲线与统计仍可查看。" }
        return ""
    }

    var body: some View {
        VStack(alignment: .leading, spacing: family == .systemLarge ? 10 : 6) {
            VStack(alignment: .leading, spacing: family == .systemLarge ? 10 : 6) {
                HStack(alignment: .firstTextBaseline) {
                    Text(entry.snapshot?.dashboard.latest?.display ?? "—")
                        .font(.system(size: family == .systemLarge ? 38 : 28, weight: .semibold, design: .rounded)).monospacedDigit()
                    Text(entry.snapshot?.dashboard.latest?.displayTrend ?? "→").font(.title2)
                    Text("mmol/L").font(.caption2).foregroundStyle(MirrorPalette.muted)
                    Spacer()
                    VStack(alignment: .trailing) {
                        Text(stale ? "读数待更新" : "血糖镜像").font(.caption.weight(.medium))
                        if let latest = entry.snapshot?.dashboard.latest {
                            Text(DisplayTime.time(latest.date)).font(.caption2).monospacedDigit().foregroundStyle(MirrorPalette.muted)
                        }
                    }
                }.foregroundStyle(stale ? Color.gray : MirrorPalette.blue)
                if let dashboard = entry.snapshot?.dashboard {
                    GlucoseChart(dashboard: dashboard, compact: true).frame(maxHeight: .infinity)
                    HStack(spacing: 12) {
                        Text("区间 \(metricText(dashboard.metrics?.inRangePercent, suffix: "%", decimals: 0))").foregroundStyle(MirrorPalette.blue)
                        Text("均值 \(metricText(dashboard.metrics?.mean))").foregroundStyle(MirrorPalette.violet)
                        if family == .systemLarge { Text("覆盖 \(metricText(dashboard.metrics?.coveragePercent, suffix: "%", decimals: 0))").foregroundStyle(MirrorPalette.muted) }
                    }.font(.caption2)
                } else {
                    Spacer()
                    Label("打开血糖镜像完成连接", systemImage: "waveform.path.ecg").font(.caption).foregroundStyle(MirrorPalette.muted)
                    Text("暂时无法连接时，将保留最近一次同步的数据。")
                        .font(.caption2).foregroundStyle(MirrorPalette.muted)
                    Spacer()
                }
            }.mirrorCard(padding: family == .systemLarge ? 12 : 8)
            if let dashboard = entry.snapshot?.dashboard {
                if family == .systemLarge {
                    VStack(alignment: .leading, spacing: 7) {
                        Text("每日观察 · \(dashboard.analysis?.reportDate ?? "未生成") · \(dashboard.analysis?.displayStatus ?? "积累数据中")")
                            .font(.caption.weight(.semibold)).lineLimit(1).foregroundStyle(MirrorPalette.violet)
                        if !reportSummary.isEmpty { Text(reportSummary).font(.caption).lineLimit(3) }
                        if let limitation = dashboard.analysis?.limitations?.first, !limitation.isEmpty {
                            Text(limitation).font(.caption2).foregroundStyle(MirrorPalette.muted).lineLimit(2)
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading).mirrorCard(padding: 12)
                } else {
                    Text("日报 \(dashboard.analysis?.reportDate ?? "未生成") · \(dashboard.analysis?.displayStatus ?? "积累数据中")\(reportSummary.isEmpty ? "" : " · " + reportSummary)")
                        .font(.caption2).lineLimit(2).foregroundStyle(MirrorPalette.muted).padding(.horizontal, 4)
                }
            }
        }
        .foregroundStyle(MirrorPalette.ink)
        .environment(\.colorScheme, .light)
        .containerBackground(MirrorPalette.background, for: .widget)
        .widgetURL(URL(string: "ottaimirror://dashboard"))
    }
}

#if !PREVIEW_TOOL
@main
struct GlucoseWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: SnapshotStore.kind, provider: GlucoseProvider()) { entry in
            GlucoseWidgetView(entry: entry)
        }
        .configurationDisplayName("血糖镜像")
        .description("最新血糖、24 小时曲线和每日趋势观察。")
        .supportedFamilies([.systemMedium, .systemLarge])
    }
}
#endif
