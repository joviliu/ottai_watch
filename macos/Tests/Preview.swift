import AppKit
import SwiftUI
import WidgetKit

@main
struct PreviewTool {
    @MainActor static func main() throws {
        let now = Date()
        let readings: [Reading] = (0..<288).map { index in
            let date = now.addingTimeInterval(Double(index - 287) * 300)
            let wave = 0.45 * sin(Double(index) / 14.0)
            let bump = index > 200 && index < 225 ? 1.8 * sin(Double(index - 200) / 25.0 * Double.pi) : 0.0
            return Reading(sourceAt: date.timeIntervalSince1970 * 1000, value: 6.2 + wave + bump, trend: "→")
        }
        let end = now.timeIntervalSince1970 * 1000
        let heart: [HeartRateBin] = (0..<72).compactMap { i in
            if i % 7 == 0 || i < 10 { return nil }
            let at = end - Double(72-i) * 1200000
            let bpm = 65 + 13 * sin(Double(i)/9) + (i > 50 && i < 58 ? 35 : 0)
            return HeartRateBin(startAt: at-60000, endAt: at+60000, mean: bpm,
                min: bpm-2, max: bpm+3, sampleCount: 2, firstSampleAt: at-30000, lastSampleAt: at+30000)
        }
        let stepBins: [ActivityPlotBin] = (0..<96).compactMap { i in
            guard (20..<29).contains(i) || (62..<70).contains(i) || (82..<88).contains(i) else { return nil }
            let at = end - Double(96-i)*900000
            return ActivityPlotBin(startAt: at, endAt: at+900000, count: Double(30 + i%9*25), recordCount: 3)
        }
        let energyBins: [ActivityPlotBin] = (0..<48).compactMap { i in
            guard (10..<15).contains(i) || (31..<35).contains(i) || (41..<44).contains(i) else { return nil }
            let at = end - Double(48-i)*1800000
            return ActivityPlotBin(startAt: at, endAt: at+1800000, energyKcal: Double(4+i%6), recordCount: 1)
        }
        let activity = ActivityData(heartRate: heart, plot: ActivityPlot(periodStart: end-86400000,
            periodEnd: end, intervalMinutes: 15, steps: stepBins, activeCalories: [],
            activeCalories30m: energyBins, activeCalories30mIntervalMinutes: 30,
            activeCalories30mOmittedRecordCount: 0, activeCalories30mTruncated: false),
            sourceByKind: ["heart_rate":"health_connect", "steps":"phone_steps", "active_calories":"health_connect"])
        let dashboard = Dashboard(schemaVersion: 1, serverAt: now.timeIntervalSince1970 * 1000,
            latest: readings.last, readings: readings,
            metrics: Metrics(coveragePercent: 100, sampleCount: 288, mean: 6.4, min: 5.7, max: 8.1, cvPercent: 12, inRangePercent: 98),
            comparison: nil,
            analysis: Analysis(status: "ready", reportDate: "合成示例", summary: "最近一天波动较平稳。长期趋势需要结合足够的历史覆盖率观察；本图仅为合成预览。", sections: [], limitations: [], sources: []), activity: activity)
        let entry = GlucoseEntry(date: now, snapshot: CachedDashboard(fetchedAt: now, dashboard: dashboard))
        let output = CommandLine.arguments.dropFirst().first ?? "macos/build/widget-synthetic.png"
        try render(GlucoseWidgetView(entry: entry, familyOverride: .systemLarge)
            .padding(16).frame(width: 360, height: 376).background(MirrorPalette.background), output: output)
        let base = URL(fileURLWithPath: output).deletingPathExtension().path
        try render(GlucoseWidgetView(entry: entry, familyOverride: .systemMedium)
            .padding(10).frame(width: 360, height: 170).background(MirrorPalette.background), output: base+"-medium.png")
        try render(GlucoseChart(dashboard: dashboard, compact: true).frame(width: 402, height: 270)
            .padding(16).background(Color.white), output: base+"-chart.png")
        print("Rendered synthetic large/medium widgets and shared activity chart")
    }
    @MainActor private static func render<V: View>(_ view: V, output: String) throws {
        let renderer = ImageRenderer(content: view)
        renderer.scale = 2
        guard let image = renderer.nsImage, let tiff = image.tiffRepresentation,
              let bitmap = NSBitmapImageRep(data: tiff), let data = bitmap.representation(using: .png, properties: [:]) else { throw MirrorError.unavailable }
        try data.write(to: URL(fileURLWithPath: output))
    }
}
