import SwiftUI
import Charts

struct GlucoseChart: View {
    let dashboard: Dashboard
    var compact = false
    var miniature = false
    private let heartColor = Color(red: 191/255, green: 145/255, blue: 189/255)
    private let stepColor = Color(red: 131/255, green: 189/255, blue: 166/255)
    private let energyColor = Color(red: 215/255, green: 170/255, blue: 100/255)
    private let axisWidth: CGFloat = 34
    private var end: Date { Date(timeIntervalSince1970: dashboard.serverAt / 1000) }
    private var start: Date { end.addingTimeInterval(-86400) }
    private var values: [PlotPoint] { observedPoints(dashboard.readings) }
    private var heart: [HeartRateBin] {
        (dashboard.activity?.heartRate ?? []).filter { $0.date >= start && $0.date <= end }
    }
    private var heartRange: ClosedRange<Double> { dashboard.activity?.heartRateRange ?? 40...100 }
    private var steps: [ActivityPlotBin] { (dashboard.activity?.plot?.steps ?? []).filter { $0.start >= start && $0.start < end && $0.count != nil } }
    private var energy: [ActivityPlotBin] { (dashboard.activity?.plot?.activeCalories ?? []).filter { $0.start >= start && $0.start < end && $0.energyKcal != nil } }
    private var coarse: Int { dashboard.activity?.plot?.omittedRecordCount ?? 0 }
    private var overlap: Bool { (steps + energy).contains { $0.potentialOverlap == true } }
    private var ticks: [Date] { (compact ? [0.0,12,24] : [0.0,6,12,18,24]).map { start.addingTimeInterval($0 * 3600) } }
    private var glucoseTicks: [Double] { dashboard.glucosePlotUpperBound > 16 ? [0, dashboard.glucosePlotUpperBound/2, dashboard.glucosePlotUpperBound] : [3.9,7.8,12] }

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
        GeometryReader { geometry in
            let extended = dashboard.activity != nil
            let spacing: CGFloat = miniature ? 2 : 6
            let header: CGFloat = miniature ? 10 : 13
            let footer: CGFloat = miniature ? 10 : 15
            let note: CGFloat = extended && !miniature ? 15 : 0
            let available = max(30, geometry.size.height - footer - note - (extended ? 3 * header + 7 * spacing : header + spacing))
            let glucoseHeight = extended ? available * (miniature ? 0.64 : 0.58) : available
            let heartHeight = available * (miniature ? 0.18 : 0.22)
            let activityHeight = available - glucoseHeight - heartHeight
            if miniature && geometry.size.height < 150 && extended {
                let trackHeight = max(24, geometry.size.height - 16)
                VStack(spacing: 2) {
                    glucoseTrack(dense: true).frame(height: trackHeight * 0.55)
                    heartTrack.frame(height: trackHeight * 0.20)
                    VStack(spacing: 1) {
                        activityTrack(steps, value: { $0.count ?? 0 }, color: stepColor, unit: "步")
                        activityTrack(energy, value: { $0.energyKcal ?? 0 }, color: energyColor, unit: "kcal")
                    }.frame(height: trackHeight * 0.25)
                    timeAxis.frame(height: 10)
                }
            } else {
              VStack(alignment: .leading, spacing: spacing) {
                trackTitle("血糖", unit: "mmol/L", color: MirrorPalette.blue).frame(height: header)
                glucoseTrack().frame(height: glucoseHeight)
                if extended {
                    trackTitle("心率", unit: "bpm", color: heartColor, detail: miniature ? nil : "实测采样").frame(height: header)
                    heartTrack.frame(height: max(18, heartHeight))
                    activityTitle.frame(height: header)
                    VStack(spacing: 2) {
                        activityTrack(steps, value: { $0.count ?? 0 }, color: stepColor, unit: "步")
                        activityTrack(energy, value: { $0.energyKcal ?? 0 }, color: energyColor, unit: "kcal")
                    }.frame(height: max(22, activityHeight))
                }
                timeAxis.frame(height: footer)
                if extended && !miniature {
                    Text(overlap ? "相对原始记录量，非运动强度 · 含可能重叠记录" : coarse > 0 ? "相对记录量，非运动强度 · 另有粗粒度／跨时段汇总" : "相对记录量，非运动强度 · 空白不代表静止")
                        .font(.system(size: 9)).foregroundStyle(MirrorPalette.muted).lineLimit(1).frame(height: note)
                }
              }
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("过去24小时，共用时间轴。血糖为独立mmol/L刻度，心率为独立bpm刻度，仅显示实际采样。绿色步数和橙色估算活动热量分别缩放，表示记录线索，不能推断运动强度；缺测不补造数据。")
    }

    private func trackTitle(_ name: String, unit: String, color: Color, detail: String? = nil) -> some View {
        HStack(spacing: 4) {
            Circle().fill(color).frame(width: 4, height: 4)
            Text(name).foregroundStyle(color)
            Text(unit).foregroundStyle(MirrorPalette.muted)
            if let detail { Text("· " + detail).foregroundStyle(MirrorPalette.muted) }
            Spacer()
        }.font(.system(size: miniature ? 8 : 10, weight: .medium))
    }
    private var activityTitle: some View {
        HStack(spacing: miniature ? 5 : 8) {
            Text(miniature ? "相对活动线索" : "活动线索").foregroundStyle(MirrorPalette.muted)
            Text("● 步数").foregroundStyle(stepColor)
            Text("● 活动能量").foregroundStyle(energyColor)
            if !miniature { Text("15分钟分组").foregroundStyle(MirrorPalette.muted) }
            Spacer()
        }.font(.system(size: miniature ? 8 : 10, weight: .medium)).lineLimit(1)
    }

    private func glucoseTrack(dense: Bool = false) -> some View {
        HStack(spacing: 4) {
            Chart {
                RectangleMark(xStart: .value("开始", start), xEnd: .value("结束", end),
                              yStart: .value("观察下界", 3.9), yEnd: .value("观察上界", 7.8))
                    .foregroundStyle(MirrorPalette.blue.opacity(0.065))
                ForEach(reference) { point in
                    LineMark(x: .value("时间", point.date), y: .value("历史参照", point.value), series: .value("参照", "history-\(point.segment)"))
                        .foregroundStyle(MirrorPalette.violet.opacity(0.22)).lineStyle(StrokeStyle(lineWidth: miniature ? 1 : 1.5))
                }
                ForEach(values) { point in
                    LineMark(x: .value("时间", point.date), y: .value("血糖", point.value), series: .value("片段", "current-\(point.segment)"))
                        .foregroundStyle(MirrorPalette.blue).lineStyle(StrokeStyle(lineWidth: miniature ? 1.8 : 2.4, lineCap: .round, lineJoin: .round))
                }
                RuleMark(y: .value("下界", 3.9)).foregroundStyle(Color.gray.opacity(0.3)).lineStyle(StrokeStyle(lineWidth: 0.6, dash: [3,3]))
                RuleMark(y: .value("上界", 7.8)).foregroundStyle(Color.gray.opacity(0.3)).lineStyle(StrokeStyle(lineWidth: 0.6, dash: [3,3]))
                if let latest = dashboard.latest, latest.date >= start, latest.date <= end {
                    PointMark(x: .value("最新时间", latest.date), y: .value("最新值", latest.value))
                        .foregroundStyle(latest.isStale(at: Date()) ? Color.gray : MirrorPalette.blue).symbolSize(miniature ? 14 : 28)
                }
            }.chartXScale(domain: start...end, range: .plotDimension(startPadding: 4, endPadding: 4))
                .chartYScale(domain: 0...dashboard.glucosePlotUpperBound).chartLegend(.hidden)
                .chartXAxis(.hidden).chartYAxis(.hidden)
            axis(dense ? [7.8] : glucoseTicks, range: 0...dashboard.glucosePlotUpperBound)
        }
    }
    private var heartTrack: some View {
        HStack(spacing: 4) {
            Chart {
                ForEach(heart) { bin in
                    if bin.min < bin.max {
                        RuleMark(x: .value("采样时间", bin.date), yStart: .value("最低心率", bin.min), yEnd: .value("最高心率", bin.max))
                            .foregroundStyle(heartColor.opacity(0.45)).lineStyle(StrokeStyle(lineWidth: miniature ? 1 : 2))
                    }
                    PointMark(x: .value("采样时间", bin.date), y: .value("心率", bin.mean))
                        .foregroundStyle(heartColor).symbolSize(miniature ? 8 : 15)
                }
            }.chartXScale(domain: start...end, range: .plotDimension(startPadding: 4, endPadding: 4))
                .chartYScale(domain: heartRange).chartXAxis(.hidden).chartYAxis(.hidden).chartLegend(.hidden)
                .overlay(alignment: .leading) {
                    if heart.isEmpty { Text("暂无心率采样").font(.system(size: miniature ? 8 : 10)).foregroundStyle(MirrorPalette.muted.opacity(0.75)).padding(.leading, 5) }
                }
                .background(heartColor.opacity(0.035), in: RoundedRectangle(cornerRadius: 4))
            if miniature {
                Text("bpm").font(.system(size: 7)).foregroundStyle(heartColor).frame(width: axisWidth, alignment: .leading)
            } else {
                axis([heartRange.lowerBound, heartRange.upperBound], range: heartRange)
            }
        }
    }
    private func activityTrack(_ bins: [ActivityPlotBin], value: @escaping (ActivityPlotBin) -> Double, color: Color, unit: String) -> some View {
        let highest = max(1, bins.map(value).max() ?? 1)
        return HStack(spacing: 4) {
            Chart {
                ForEach(bins) { bin in
                    if value(bin) > 0 {
                        RectangleMark(xStart: .value("区间起点分组", bin.start), xEnd: .value("分组结束", bin.end),
                                      yStart: .value("基线", 0), yEnd: .value(unit, value(bin)))
                            .foregroundStyle(color.opacity(bin.potentialOverlap == true ? 0.35 : 0.75)).cornerRadius(1)
                    }
                }
            }.chartXScale(domain: start...end, range: .plotDimension(startPadding: 4, endPadding: 4))
                .chartYScale(domain: 0...highest).chartXAxis(.hidden).chartYAxis(.hidden).chartLegend(.hidden)
                .background(color.opacity(0.035), in: RoundedRectangle(cornerRadius: 3))
                .overlay(alignment: .leading) {
                    if bins.isEmpty {
                        Text(unit == "步" ? "暂无步数分时记录" : "暂无能量分时记录")
                            .font(.system(size: miniature ? 6 : 9)).foregroundStyle(MirrorPalette.muted.opacity(0.7)).padding(.leading, 5)
                    }
                }
            Text(unit).font(.system(size: miniature ? 7 : 9)).foregroundStyle(color).frame(width: axisWidth, alignment: .leading)
        }
    }
    private func axis(_ values: [Double], range: ClosedRange<Double>) -> some View {
        GeometryReader { geometry in
            ForEach(values, id: \.self) { value in
                Text(metricText(value, decimals: value == floor(value) ? 0 : 1))
                    .font(.system(size: miniature ? 7 : 9)).monospacedDigit().foregroundStyle(MirrorPalette.muted)
                    .frame(width: axisWidth, alignment: .leading)
                    .position(x: axisWidth/2, y: max(5, min(geometry.size.height-5, geometry.size.height * (1-(value-range.lowerBound)/(range.upperBound-range.lowerBound)))))
            }
        }.frame(width: axisWidth)
    }
    private var timeAxis: some View {
        HStack(spacing: 4) {
            HStack(spacing: 0) {
                ForEach(Array(ticks.enumerated()), id: \.offset) { index, date in
                    if index > 0 { Spacer(minLength: 0) }
                    Text(DisplayTime.time(date)).font(.system(size: miniature ? 7 : 9)).monospacedDigit().foregroundStyle(MirrorPalette.muted)
                }
            }.padding(.horizontal, 4)
            Color.clear.frame(width: axisWidth)
        }
    }
}
