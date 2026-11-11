import SwiftUI
import Charts

struct GlucoseChart: View {
    let dashboard: Dashboard
    var compact = false
    var miniature = false
    var eventEditor: ((ChartEventSelection) -> AnyView)? = nil
    @State private var hoverDate: Date?
    @State private var selection: ChartEventSelection?
    @State private var selectionAnchor = CGPoint.zero
    private var interactive: Bool { eventEditor != nil && !miniature }
    private var markers: [LifestyleEvent] {
        (dashboard.events ?? []).filter { $0.date >= start && $0.date <= end }.sorted { $0.at < $1.at }
    }
    private let heartColor = Color(red: 191/255, green: 145/255, blue: 189/255)
    private let stepColor = Color(red: 131/255, green: 189/255, blue: 166/255)
    private let energyColor = Color(red: 215/255, green: 170/255, blue: 100/255)
    private let sleepColor = Color(red: 168/255, green: 154/255, blue: 203/255)
    private let exerciseColor = Color(red: 119/255, green: 184/255, blue: 160/255)
    private let axisWidth: CGFloat = 34
    private var end: Date { Date(timeIntervalSince1970: dashboard.serverAt / 1000) }
    private var start: Date { end.addingTimeInterval(-86400) }
    private var values: [PlotPoint] { observedPoints(dashboard.readings) }
    private var heart: [HeartRateBin] {
        (dashboard.activity?.heartRate ?? []).filter { $0.date >= start && $0.date <= end }
    }
    private var heartRange: ClosedRange<Double> { dashboard.activity?.heartRateRange ?? 40...100 }
    private var steps: [ActivityPlotBin] { (dashboard.activity?.plot?.steps ?? []).filter { $0.start >= start && $0.start < end && $0.count != nil } }
    private var energy: [ActivityPlotBin] { (dashboard.activity?.plot?.energyBins ?? []).filter { $0.start >= start && $0.start < end && $0.energyKcal != nil } }
    private var energyInterval: Int { dashboard.activity?.plot?.energyIntervalMinutes ?? 15 }
    private var coarse: Int { dashboard.activity?.plot?.omittedRecordCount ?? 0 }
    private var overlap: Bool { (steps + energy).contains { $0.potentialOverlap == true } }
    private var sleepSessions: [ActivitySession] {
        (dashboard.activity?.sleepSessions ?? []).filter { $0.clipped(start: start, end: end) != nil }
    }
    private var exerciseSessions: [ActivitySession] {
        (dashboard.activity?.exerciseSessions ?? []).filter { $0.clipped(start: start, end: end) != nil }
    }
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
                        activityTrack(energy, value: { $0.energyKcal ?? 0 }, color: energyColor, unit: "kcal", intervalMinutes: energyInterval)
                    }.frame(height: trackHeight * 0.25)
                    timeAxis.frame(height: 10)
                }
            } else {
              VStack(alignment: .leading, spacing: spacing) {
                glucoseTitle.frame(height: header)
                glucoseTrack().frame(height: glucoseHeight)
                if extended {
                    trackTitle("心率", unit: "bpm", color: heartColor, detail: miniature ? nil : "实测采样").frame(height: header)
                    heartTrack.frame(height: max(18, heartHeight))
                    activityTitle.frame(height: header)
                    VStack(spacing: 2) {
                        activityTrack(steps, value: { $0.count ?? 0 }, color: stepColor, unit: "步")
                        activityTrack(energy, value: { $0.energyKcal ?? 0 }, color: energyColor, unit: "kcal", intervalMinutes: energyInterval)
                    }.frame(height: max(22, activityHeight))
                }
                timeAxis.frame(height: footer)
                if extended && !miniature {
                    Text(dashboard.activity?.plot?.activeCalories30mTruncated == true ? "活动分组较多，仅显示部分 · 非运动强度" : overlap ? "相对原始记录量，非运动强度 · 含可能重叠记录" : coarse > 0 ? "相对记录量，非运动强度 · 另有粗粒度／跨时段汇总" : "相对记录量，非运动强度 · 空白不代表静止")
                        .font(.system(size: 9)).foregroundStyle(MirrorPalette.muted).lineLimit(1).frame(height: note)
                }
              }
            }
        }
        .accessibilityElement(children: interactive ? .contain : .combine)
        .accessibilityLabel("过去24小时，共用时间轴。淡紫色区间是Health Connect睡眠记录，淡绿色是锻炼会话；睡眠记录可能包含清醒时间。血糖为独立mmol/L刻度，心率为独立bpm刻度，仅显示实际采样。绿色步数和橙色估算活动热量分别缩放，表示记录线索，不能推断运动强度；缺测不补造数据。")
    }

    private var glucoseTitle: some View {
        HStack(spacing: 7) {
            trackTitle("血糖", unit: "mmol/L", color: MirrorPalette.blue)
            if !sleepSessions.isEmpty {
                Label("睡眠", systemImage: "moon.zzz.fill").foregroundStyle(sleepColor)
                    .help("Health Connect睡眠记录区间，可能包含清醒时间")
            }
            if !exerciseSessions.isEmpty {
                Label("锻炼", systemImage: "figure.run").foregroundStyle(exerciseColor)
                    .help("Health Connect锻炼会话区间")
            }
        }.font(.system(size: miniature ? 8 : 10, weight: .medium)).lineLimit(1)
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
            Text("● 步数15分").foregroundStyle(stepColor)
            Text("● 能量\(energyInterval)分").foregroundStyle(energyColor)
            if !miniature { Text("起点分组").foregroundStyle(MirrorPalette.muted) }
            Spacer()
        }.font(.system(size: miniature ? 8 : 10, weight: .medium)).lineLimit(1)
    }

    private func glucoseTrack(dense: Bool = false) -> some View {
        VStack(spacing: 3) {
          HStack(spacing: 4) {
            Chart {
                RectangleMark(xStart: .value("开始", start), xEnd: .value("结束", end),
                              yStart: .value("观察下界", 3.9), yEnd: .value("观察上界", 7.8))
                    .foregroundStyle(MirrorPalette.blue.opacity(0.065))
                ForEach(sleepSessions) { session in
                    if let interval = session.clipped(start: start, end: end) {
                        RectangleMark(xStart: .value("睡眠开始", interval.start), xEnd: .value("睡眠结束", interval.end),
                                      yStart: .value("区间下界", 0), yEnd: .value("区间上界", dashboard.glucosePlotUpperBound))
                            .foregroundStyle(sleepColor.opacity(0.10))
                    }
                }
                ForEach(exerciseSessions) { session in
                    if let interval = session.clipped(start: start, end: end) {
                        RectangleMark(xStart: .value("锻炼开始", interval.start), xEnd: .value("锻炼结束", interval.end),
                                      yStart: .value("区间下界", 0), yEnd: .value("区间上界", dashboard.glucosePlotUpperBound))
                            .foregroundStyle(exerciseColor.opacity(0.13))
                    }
                }
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
                if interactive {
                    ForEach(markers) { marker in
                        RuleMark(x: .value("用户记录", marker.date))
                            .foregroundStyle(marker.type.tint.opacity(0.16))
                            .lineStyle(StrokeStyle(lineWidth: 1, dash: [2, 3]))
                        PointMark(x: .value("记录时间", marker.date), y: .value("记录", 0.55))
                            .foregroundStyle(marker.type.tint).symbolSize(13)
                    }
                }
                if let latest = dashboard.latest, latest.date >= start, latest.date <= end {
                    PointMark(x: .value("最新时间", latest.date), y: .value("最新值", latest.value))
                        .foregroundStyle(latest.isStale(at: Date()) ? Color.gray : MirrorPalette.blue).symbolSize(miniature ? 14 : 28)
                }
            }.chartXScale(domain: start...end, range: .plotDimension(startPadding: 4, endPadding: 4))
                .chartYScale(domain: 0...dashboard.glucosePlotUpperBound).chartLegend(.hidden)
                .chartXAxis(.hidden).chartYAxis(.hidden)
                .chartOverlay { proxy in
                    GeometryReader { geometry in
                        if interactive, let anchor = proxy.plotFrame {
                            let frame = geometry[anchor]
                            let cursorDate = selection?.date ?? hoverDate
                            ZStack(alignment: .topLeading) {
                                if let cursorDate, let position = proxy.position(forX: cursorDate) {
                                    Path { path in
                                        path.move(to: CGPoint(x: frame.minX + position, y: frame.minY))
                                        path.addLine(to: CGPoint(x: frame.minX + position, y: frame.maxY))
                                    }.stroke(MirrorPalette.ink.opacity(0.42), style: StrokeStyle(lineWidth: 0.8, dash: [3, 3]))
                                    Text(DisplayTime.time(cursorDate))
                                        .font(.system(size: 10, weight: .semibold)).monospacedDigit()
                                        .foregroundStyle(MirrorPalette.blue).padding(.horizontal, 7).padding(.vertical, 4)
                                        .background(.white, in: Capsule()).shadow(color: .black.opacity(0.08), radius: 3, y: 1)
                                        .position(x: min(max(frame.minX + position, 28), geometry.size.width - 28), y: frame.minY + 10)
                                        .allowsHitTesting(false)
                                }
                                Rectangle().fill(.clear).contentShape(Rectangle())
                                    .onContinuousHover { phase in
                                        switch phase {
                                        case .active(let location): hoverDate = chartDate(at: location, proxy: proxy, frame: frame)
                                        case .ended: hoverDate = nil
                                        }
                                    }
                                    .onTapGesture(coordinateSpace: .local) { location in
                                        guard let date = chartDate(at: location, proxy: proxy, frame: frame) else { return }
                                        selectionAnchor = location
                                        selection = ChartEventSelection(date: date, event: nil)
                                    }
                                    .accessibilityHidden(true)
                                Color.clear.frame(width: 1, height: 1)
                                    .popover(item: $selection, arrowEdge: .bottom) { selected in
                                        if let eventEditor { eventEditor(selected) }
                                    }
                                    .position(selectionAnchor)
                            }
                        }
                    }
                }
            axis(dense ? [7.8] : glucoseTicks, range: 0...dashboard.glucosePlotUpperBound)
          }
          if interactive, let eventEditor {
            HStack(spacing: 7) {
                ChartEventChip(date: end, event: nil, editor: eventEditor)
                if markers.isEmpty {
                    Text("点击曲线，记录大约时间").font(.system(size: 9)).foregroundStyle(MirrorPalette.muted)
                    Spacer()
                } else {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 6) {
                            ForEach(markers) { marker in
                                ChartEventChip(date: marker.date, event: marker, editor: eventEditor)
                            }
                        }
                    }
                    if dashboard.eventsTruncated == true {
                        Image(systemName: "ellipsis.circle").font(.system(size: 10)).foregroundStyle(MirrorPalette.muted)
                            .help("仅显示最近的时间标记，历史记录仍已保存")
                    }
                }
            }.frame(height: 21)
          }
        }
    }

    private func chartDate(at location: CGPoint, proxy: ChartProxy, frame: CGRect) -> Date? {
        guard frame.contains(location), let left = proxy.position(forX: start), let right = proxy.position(forX: end), right > left else { return nil }
        return ChartSelection.date(at: min(max(Double(location.x - frame.minX - left), 0), Double(right - left)),
                                   width: Double(right - left), start: start, end: end)
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
    private func activityTrack(_ bins: [ActivityPlotBin], value: @escaping (ActivityPlotBin) -> Double, color: Color, unit: String, intervalMinutes: Int? = nil) -> some View {
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
            Text(miniature && intervalMinutes != nil ? "\(unit)·\(intervalMinutes!)m" : unit)
                .font(.system(size: miniature ? 7 : 9)).foregroundStyle(color).frame(width: axisWidth, alignment: .leading)
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

private struct ChartEventChip: View {
    let date: Date
    let event: LifestyleEvent?
    let editor: (ChartEventSelection) -> AnyView
    @State private var showing = false
    var body: some View {
        Button { showing = true } label: {
            HStack(spacing: 4) {
                Image(systemName: event?.type.symbol ?? "plus.circle.fill")
                Text(event.map { DisplayTime.time($0.date) } ?? "记录").monospacedDigit()
            }.font(.system(size: 9, weight: .medium)).padding(.horizontal, 6).padding(.vertical, 4)
                .foregroundStyle(event?.type.tint ?? MirrorPalette.blue)
                .background((event?.type.tint ?? MirrorPalette.blue).opacity(0.08), in: Capsule())
        }.buttonStyle(.plain)
            .help(event.map { $0.type.title + " · " + DisplayTime.dateTime($0.date) + ($0.note.isEmpty ? "" : " · " + $0.note) } ?? "记录进餐、睡眠或活动")
            .accessibilityLabel(event.map { "编辑" + $0.type.title + DisplayTime.dateTime($0.date) } ?? "添加时间记录")
            .popover(isPresented: $showing, arrowEdge: .bottom) { editor(ChartEventSelection(date: date, event: event)) }
    }
}
