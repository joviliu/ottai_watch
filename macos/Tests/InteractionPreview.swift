import AppKit
import SwiftUI

@main
struct InteractionPreview {
    @MainActor static func main() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("ottai-interaction-preview-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        defer { try? FileManager.default.removeItem(at: folder) }
        let store = ConnectionStore(url: folder.appendingPathComponent("connection.json"))
        try store.save(ConnectionConfiguration(baseURL: "https://example.invalid/ottai", readToken: "synthetic-read", analysisToken: String(repeating: "p", count: 40)))
        let now = Date(), end = now.timeIntervalSince1970 * 1000
        let readings: [Reading] = (0..<288).map { index in
            let at = end - Double(287-index) * 300000.0
            let wave = 0.25 * sin(Double(index) / 13.0)
            let bump = index > 198 && index < 239 ? 1.7 * sin(Double(index-198) / 41.0 * Double.pi) : 0.0
            return Reading(sourceAt: at, value: 6.1 + wave + bump, trend: "→")
        }
        let events = [
            LifestyleEvent(id: "synthetic-sleep", type: .sleep, at: end-16*3600000, note: ""),
            LifestyleEvent(id: "synthetic-wake", type: .wake, at: end-8*3600000, note: ""),
            LifestyleEvent(id: "synthetic-meal", type: .meal, at: end-6*3600000, note: "大约时间", meal: MealDetails(foods: "米饭、青菜和鸡肉", estimatedKcalMin: 450, estimatedKcalMax: 600, source: "photo_estimate")),
            LifestyleEvent(id: "synthetic-walk", type: .exercise, at: end-4*3600000, note: "散步")]
        let report = Analysis(status: "ready", generatedAt: end, reportDate: "合成预览", summary: "整体较平稳，主要关注一次持续较长的升高。", sections: [], limitations: [], sources: [], periodStart: end-86400000, periodEnd: end, trigger: "manual", highlights: [
            AnalysisHighlight(title: "这次升高值得继续观察", text: "峰值后的回落较慢，下一餐可结合进餐标记做比较。", severity: "watch", action: "记录主食份量和大约时间。"),
            AnalysisHighlight(title: "夜间曲线较平稳", text: "记录的睡眠时段没有明显持续升高。", severity: "positive", action: nil)])
        let heart = (0..<12).map { index in
            let at = end - Double(12-index)*3600000
            return HeartRateBin(startAt: at, endAt: at+300000, mean: 65+Double(index%4)*4, min: 62+Double(index%4)*4, max: 69+Double(index%4)*4, sampleCount: 2, firstSampleAt: at+1000, lastSampleAt: at+250000)
        }
        let dashboard = Dashboard(schemaVersion: 1, serverAt: end, latest: readings.last, readings: readings,
            metrics: Metrics(coveragePercent: 100, mean: 6.3, min: 5.8, max: 8.0, inRangePercent: 98), analysis: report,
            dailyAnalysis: report, rollingAnalysis: report, manualAnalysis: ManualAnalysisState(eligible: true, status: "ready", reason: ""),
            activity: ActivityData(heartRate: heart, plot: ActivityPlot(steps: [], activeCalories30m: [], activeCalories30mIntervalMinutes: 30)), events: events)
        let cache = folder.appendingPathComponent("dashboard.json")
        try SnapshotStore.save(CachedDashboard(fetchedAt: now, dashboard: dashboard), at: cache)
        let model = AppModel(connectionStore: store, snapshotURL: cache, automaticallyRefresh: false, reloadWidgets: {})
        let output = CommandLine.arguments.dropFirst().first ?? "macos/build/report-events-synthetic.png"
        try render(VStack(spacing: 12) {
            Text("合成资料 · 报告与时间标记布局").font(.caption).foregroundStyle(.secondary)
            GlucoseChart(dashboard: dashboard, eventEditor: { selection in AnyView(EventEditor(model: model, selection: selection)) })
                .frame(height: 360).mirrorCard()
            AnalysisPanel(model: model, compact: false)
        }.padding(20).frame(width: 700).foregroundStyle(MirrorPalette.ink).background(MirrorPalette.background)
            .preferredColorScheme(.light), output: output)
        let editorOutput = URL(fileURLWithPath: output).deletingPathExtension().path+"-editor.png"
        try render(EventEditor(model: model, selection: ChartEventSelection(date: events[2].date, event: events[2]))
            .padding(20).background(MirrorPalette.background), output: editorOutput)
        print("Rendered synthetic report highlights, event markers and event editor; no real connection or network used")
    }
    @MainActor private static func render<V: View>(_ view: V, output: String) throws {
        _ = NSApplication.shared
        let host = NSHostingView(rootView: view)
        host.appearance = NSAppearance(named: .aqua)
        host.frame = NSRect(origin: .zero, size: host.fittingSize)
        host.layoutSubtreeIfNeeded()
        guard let bitmap = host.bitmapImageRepForCachingDisplay(in: host.bounds) else { throw MirrorError.unavailable }
        host.appearance!.performAsCurrentDrawingAppearance { host.cacheDisplay(in: host.bounds, to: bitmap) }
        guard let data = bitmap.representation(using: .png, properties: [:]) else { throw MirrorError.unavailable }
        try data.write(to: URL(fileURLWithPath: output))
    }
}
