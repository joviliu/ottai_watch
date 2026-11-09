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
        let dashboard = Dashboard(schemaVersion: 1, serverAt: now.timeIntervalSince1970 * 1000,
            latest: readings.last, readings: readings,
            metrics: Metrics(coveragePercent: 100, sampleCount: 288, mean: 6.4, min: 5.7, max: 8.1, cvPercent: 12, inRangePercent: 98),
            comparison: nil,
            analysis: Analysis(status: "ready", reportDate: "合成示例", summary: "最近一天波动较平稳。长期趋势需要结合足够的历史覆盖率观察；本图仅为合成预览。", sections: [], limitations: [], sources: []))
        let view = GlucoseWidgetView(entry: GlucoseEntry(date: now, snapshot: CachedDashboard(fetchedAt: now, dashboard: dashboard)), familyOverride: .systemLarge)
            .padding(18).frame(width: 360, height: 380).background(MirrorPalette.background)
        let renderer = ImageRenderer(content: view)
        renderer.scale = 2
        guard let image = renderer.nsImage, let tiff = image.tiffRepresentation,
              let bitmap = NSBitmapImageRep(data: tiff), let data = bitmap.representation(using: .png, properties: [:]) else { throw MirrorError.unavailable }
        let output = CommandLine.arguments.dropFirst().first ?? "macos/build/widget-synthetic.png"
        try data.write(to: URL(fileURLWithPath: output))
        print("Rendered synthetic WidgetKit view")
    }
}
