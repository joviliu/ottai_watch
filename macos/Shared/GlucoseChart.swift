import SwiftUI
import Charts

struct GlucoseChart: View {
    let dashboard: Dashboard
    var compact = false
    private var end: Date { Date(timeIntervalSince1970: dashboard.serverAt / 1000) }
    private var start: Date { end.addingTimeInterval(-86400) }
    private var values: [PlotPoint] { observedPoints(dashboard.readings) }
    private var ticks: [Date] {
        let hours: [Double] = compact ? [4, 12, 20] : [3, 9, 15, 21]
        return hours.map { start.addingTimeInterval($0 * 3600) }
    }

    private var reference: [PlotPoint] {
        guard let points = dashboard.comparison?.plotPoints, !points.isEmpty else { return [] }
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: dashboard.comparison?.timezone ?? "Asia/Shanghai") ?? .current
        var result: [PlotPoint] = []
        let firstDay = calendar.startOfDay(for: start)
        for offset in 0...2 {
            guard let day = calendar.date(byAdding: .day, value: offset, to: firstDay), day <= end else { continue }
            for point in points where point.median != nil {
                guard let date = calendar.date(byAdding: .minute, value: point.minuteOfDay, to: day), date >= start, date <= end else { continue }
                result.append(PlotPoint(date: date, value: point.median!, segment: 0))
            }
        }
        var prior: Date?
        var segment = 0
        return result.sorted { $0.date < $1.date }.map { point in
            if let prior, point.date.timeIntervalSince(prior) > 1801 { segment += 1 }
            prior = point.date
            return PlotPoint(date: point.date, value: point.value, segment: segment)
        }
    }

    var body: some View {
        Chart {
            RectangleMark(xStart: .value("开始", start), xEnd: .value("结束", end),
                          yStart: .value("观察下界", 3.9), yEnd: .value("观察上界", 7.8))
                .foregroundStyle(MirrorPalette.blue.opacity(0.065))
            ForEach(reference) { point in
                LineMark(x: .value("时间", point.date), y: .value("历史参照", point.value), series: .value("参照", "history-\(point.segment)"))
                    .foregroundStyle(MirrorPalette.violet.opacity(0.22)).lineStyle(StrokeStyle(lineWidth: compact ? 1.5 : 2))
            }
            ForEach(values) { point in
                LineMark(x: .value("时间", point.date), y: .value("血糖", point.value), series: .value("片段", "current-\(point.segment)"))
                    .foregroundStyle(MirrorPalette.blue).lineStyle(StrokeStyle(lineWidth: compact ? 2 : 2.7, lineCap: .round, lineJoin: .round))
            }
            RuleMark(y: .value("下界", 3.9)).foregroundStyle(Color.gray.opacity(0.35)).lineStyle(StrokeStyle(lineWidth: 0.7, dash: [4, 4]))
            RuleMark(y: .value("上界", 7.8)).foregroundStyle(Color.gray.opacity(0.35)).lineStyle(StrokeStyle(lineWidth: 0.7, dash: [4, 4]))
            if let latest = dashboard.latest, latest.date >= start, latest.date <= end {
                PointMark(x: .value("最新时间", latest.date), y: .value("最新值", latest.value))
                    .foregroundStyle(latest.isStale(at: Date()) ? Color.gray : MirrorPalette.blue).symbolSize(compact ? 20 : 42)
            }
        }
        .chartXScale(domain: start...end, range: .plotDimension(startPadding: 8, endPadding: 8))
        .chartYScale(domain: 0...max(12, (dashboard.readings.map(\.value).max() ?? 10) + 1))
        .chartLegend(.hidden)
        .chartXAxis {
            AxisMarks(values: ticks) { value in
                AxisValueLabel {
                    if let date = value.as(Date.self) {
                        Text(DisplayTime.time(date)).font(.caption2).monospacedDigit().foregroundStyle(MirrorPalette.muted)
                    }
                }
            }
        }
        .chartYAxis {
            AxisMarks(position: .trailing, values: [3.9, 7.8, 12]) { value in
                AxisValueLabel {
                    if let number = value.as(Double.self) { Text(number, format: .number.precision(.fractionLength(0...1))) }
                }
                AxisGridLine().foregroundStyle(Color.gray.opacity(0.1))
            }
        }
        .accessibilityLabel("过去 24 小时血糖趋势。蓝色为本次读数，灰色为历史同时段中位数；缺测超过十分钟不连接。")
    }
}
