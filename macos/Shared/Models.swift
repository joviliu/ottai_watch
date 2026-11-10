import Foundation

enum DisplayTime {
    private static let clock: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = .autoupdatingCurrent
        formatter.dateFormat = "HH:mm"
        return formatter
    }()
    private static let datedClock: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = .autoupdatingCurrent
        formatter.dateFormat = "MM-dd HH:mm"
        return formatter
    }()
    static func time(_ date: Date) -> String { clock.string(from: date) }
    static func dateTime(_ date: Date) -> String { datedClock.string(from: date) }
}

struct Reading: Codable, Identifiable {
    let sourceAt: Double
    let value: Double
    let trend: String
    var id: Double { sourceAt }
    var date: Date { Date(timeIntervalSince1970: sourceAt / 1000) }
    func isStale(at now: Date) -> Bool { now.timeIntervalSince(date) > 600 || date.timeIntervalSince(now) > 120 }
    var display: String { String(format: "%.1f", value) }
    var displayTrend: String {
        let known: Set<String> = ["↑↑", "↑", "↗", "→", "↘", "↓", "↓↓", "↔", "?"]
        let text = trend.trimmingCharacters(in: .whitespacesAndNewlines)
        if known.contains(text) { return text }
        return text.first.flatMap { "↑↗→↘↓↔".contains($0) ? String($0) : nil } ?? "?"
    }
    var statusTrendSymbol: String {
        switch displayTrend {
        case "↑↑": return "chevron.up.2"
        case "↑": return "arrow.up"
        case "↗": return "arrow.up.right"
        case "→", "↔": return "arrow.right"
        case "↘": return "arrow.down.right"
        case "↓": return "arrow.down"
        case "↓↓": return "chevron.down.2"
        default: return "questionmark"
        }
    }
}

struct Metrics: Codable {
    var coveragePercent: Double?
    var sampleCount: Int?
    var mean: Double?
    var min: Double?
    var max: Double?
    var cvPercent: Double?
    var inRangePercent: Double?
}

struct ComparisonPoint: Codable, Identifiable {
    let minuteOfDay: Int
    let median: Double?
    let p25: Double?
    let p75: Double?
    let sampleDays: Int?
    var id: Int { minuteOfDay }
}

struct Comparison: Codable {
    var daysAvailable: Double?
    var timezone: String?
    var points: [ComparisonPoint]?
    var plotPoints: [ComparisonPoint] {
        guard (daysAvailable ?? 0) >= 3 else { return [] }
        return (points ?? []).filter { point in
            guard (point.sampleDays ?? 0) >= 3, let value = point.median else { return false }
            return value.isFinite && value > 0 && value <= 60
        }
    }
}

struct AnalysisSection: Codable, Identifiable {
    let title: String
    let text: String
    var id: String { title + text }
}

struct AnalysisSource: Codable, Identifiable {
    let title: String
    let url: String
    var id: String { url }
}

struct AnalysisHighlight: Codable, Identifiable {
    let title: String
    let text: String
    let severity: String
    var action: String?
    var id: String { title + text }
    var valid: Bool {
        title.count <= 24 && text.count <= 120 && (action?.count ?? 0) <= 60
            && ["info", "watch", "positive"].contains(severity)
    }
}

struct AnalysisEvidence: Codable, Identifiable {
    let topic: String
    let title: String
    let text: String
    let sourceUrl: String
    var id: String { topic }
    var valid: Bool {
        guard topic.count <= 40, title.count <= 40, text.count <= 160,
              let url = URL(string: sourceUrl), url.scheme == "https", url.host != nil,
              url.user == nil, url.password == nil else { return false }
        return true
    }
}

struct Analysis: Codable {
    let status: String
    var generatedAt: Double?
    var reportDate: String?
    var summary: String?
    var sections: [AnalysisSection]?
    var limitations: [String]?
    var sources: [AnalysisSource]?
    var dataStale: Bool?
    var periodStart: Double?
    var periodEnd: Double?
    var trigger: String?
    var highlights: [AnalysisHighlight]?
    var evidence: [AnalysisEvidence]?
    var valid: Bool {
        (highlights?.count ?? 0) <= 3 && (highlights ?? []).allSatisfy(\.valid)
            && (evidence?.count ?? 0) <= 1 && (evidence ?? []).allSatisfy(\.valid)
    }
    var periodDescription: String? {
        guard let start = periodStart, let end = periodEnd else { return nil }
        return DisplayTime.dateTime(Date(timeIntervalSince1970: start/1000))+" – "+DisplayTime.dateTime(Date(timeIntervalSince1970: end/1000))
    }
    var displayStatus: String {
        if dataStale == true { return "旧报告" }
        if status == "running" { return generatedAt == nil ? "生成中" : "生成中 · 旧结果" }
        if status == "ready" { return "已生成" }
        if status == "error" || status == "failed" { return (generatedAt != nil || reportDate != nil) ? "分析失败 · 旧报告" : "分析失败" }
        return (generatedAt != nil || reportDate != nil) ? "旧报告 · 待更新" : "积累数据中"
    }
}

enum LifestyleEventKind: String, Codable, CaseIterable, Identifiable {
    case meal, sleep, wake, exercise, note
    var id: String { rawValue }
    var title: String {
        switch self {
        case .meal: return "进餐"
        case .sleep: return "入睡"
        case .wake: return "起床"
        case .exercise: return "运动"
        case .note: return "备注"
        }
    }
    var symbol: String {
        switch self {
        case .meal: return "fork.knife"
        case .sleep: return "moon.zzz.fill"
        case .wake: return "sun.max.fill"
        case .exercise: return "figure.walk"
        case .note: return "text.bubble.fill"
        }
    }
}

struct MealDetails: Codable, Equatable {
    var foods: String
    var estimatedKcalMin: Double?
    var estimatedKcalMax: Double?
    var source: String
    static func recording(foods: String, previous: MealDetails?) -> MealDetails? {
        let text = foods.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return nil }
        if text == previous?.foods { return previous }
        return MealDetails(foods: text, source: "manual")
    }
    var valid: Bool {
        guard validEventText(foods), ["manual", "photo_estimate"].contains(source) else { return false }
        if estimatedKcalMin == nil && estimatedKcalMax == nil { return true }
        guard let low = estimatedKcalMin, let high = estimatedKcalMax else { return false }
        return low.isFinite && high.isFinite && low >= 0 && low <= high && high <= 20000
    }
}

struct LifestyleEvent: Codable, Identifiable, Equatable {
    let id: String
    var type: LifestyleEventKind
    var at: Double
    var note: String
    var meal: MealDetails?
    var updatedAt: Double?
    var date: Date { Date(timeIntervalSince1970: at / 1000) }
    var valid: Bool {
        (8...80).contains(id.utf8.count) && id.utf8.allSatisfy { (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0) || $0 == 45 || $0 == 95 }
            && at.isFinite && at > 0 && validEventText(note)
            && (updatedAt.map { $0.isFinite && $0 > 0 } ?? true) && (meal?.valid ?? true)
    }
}

struct ChartEventSelection: Identifiable {
    let id = UUID()
    let date: Date
    let event: LifestyleEvent?
}

enum ChartSelection {
    static func minuteDate(_ date: Date) -> Date { Date(timeIntervalSince1970: floor(date.timeIntervalSince1970 / 60) * 60) }
    static func date(at x: Double, width: Double, start: Date, end: Date) -> Date? {
        guard x.isFinite, width.isFinite, width > 0, end > start, x >= 0, x <= width else { return nil }
        return start.addingTimeInterval(x / width * end.timeIntervalSince(start))
    }
    static func x(for date: Date, width: Double, start: Date, end: Date) -> Double? {
        guard width.isFinite, width > 0, end > start, date >= start, date <= end else { return nil }
        return date.timeIntervalSince(start) / end.timeIntervalSince(start) * width
    }
}

private func validEventText(_ text: String) -> Bool {
    text.unicodeScalars.count <= 1000 && text.unicodeScalars.allSatisfy { $0.value >= 32 || $0.value == 9 || $0.value == 10 }
}

struct ManualAnalysisState: Codable {
    let eligible: Bool
    let status: String
    let reason: String
    var coveragePercent: Double?
    var cooldownSeconds: Double?
}

struct HeartRateBin: Codable, Identifiable {
    let startAt: Double
    let endAt: Double
    let mean: Double
    let min: Double
    let max: Double
    let sampleCount: Int
    let firstSampleAt: Double
    let lastSampleAt: Double
    var id: Double { startAt }
    var date: Date { Date(timeIntervalSince1970: (firstSampleAt + lastSampleAt) / 2000) }
    var valid: Bool {
        [startAt, endAt, mean, min, max, firstSampleAt, lastSampleAt].allSatisfy(\.isFinite)
            && startAt > 0 && startAt < endAt && firstSampleAt >= startAt && lastSampleAt <= endAt
            && firstSampleAt <= lastSampleAt && sampleCount > 0 && sampleCount <= 100000
            && min > 0 && min <= mean && mean <= max && max <= 300
    }
}

struct ActivityPlotBin: Codable, Identifiable {
    let startAt: Double
    let endAt: Double
    var count: Double?
    var energyKcal: Double?
    var recordCount: Int?
    var firstRecordStartAt: Double?
    var lastRecordEndAt: Double?
    var crossBinRecordCount: Int?
    var source: String?
    var potentialOverlap: Bool?
    var id: Double { startAt }
    var start: Date { Date(timeIntervalSince1970: startAt / 1000) }
    var end: Date { Date(timeIntervalSince1970: endAt / 1000) }
    var valid: Bool { valid(maxIntervalMillis: 900001) }
    func valid(maxIntervalMillis: Double) -> Bool {
        startAt.isFinite && endAt.isFinite && startAt > 0 && endAt > startAt && endAt - startAt <= maxIntervalMillis
            && [count, energyKcal].compactMap { $0 }.allSatisfy { $0.isFinite && $0 >= 0 && $0 <= 1e12 }
    }
}

struct ActivityPlot: Codable {
    var periodStart: Double?
    var periodEnd: Double?
    var intervalMinutes: Int?
    var steps: [ActivityPlotBin]?
    var activeCalories: [ActivityPlotBin]?
    var activeCalories30m: [ActivityPlotBin]?
    var activeCalories30mIntervalMinutes: Int?
    var activeCalories30mOmittedRecordCount: Int?
    var activeCalories30mTruncated: Bool?
    var energyBins: [ActivityPlotBin] { activeCalories30m ?? activeCalories ?? [] }
    var energyIntervalMinutes: Int { activeCalories30m == nil ? 15 : 30 }
    var coarseStepRecordCount: Int?
    var coarseActiveCalorieRecordCount: Int?
    var futureEndStepRecordCount: Int?
    var futureEndActiveCalorieRecordCount: Int?
    var crossPeriodStepRecordCount: Int?
    var crossPeriodActiveCalorieRecordCount: Int?
    var instantStepRecordCount: Int?
    var instantActiveCalorieRecordCount: Int?
    var omittedRecordCount: Int {
        let steps = [coarseStepRecordCount, futureEndStepRecordCount, crossPeriodStepRecordCount,
                     instantStepRecordCount].compactMap { $0 }.reduce(0,+)
        let energy = activeCalories30m == nil
            ? [coarseActiveCalorieRecordCount, futureEndActiveCalorieRecordCount,
               crossPeriodActiveCalorieRecordCount, instantActiveCalorieRecordCount].compactMap { $0 }.reduce(0,+)
            : activeCalories30mOmittedRecordCount ?? 0
        return steps + energy
    }
}

struct ActivityData: Codable {
    var heartRate: [HeartRateBin]?
    var plot: ActivityPlot?
    var sourceByKind: [String: String]?
    var valid: Bool {
        (heartRate?.count ?? 0) <= 288 && (heartRate ?? []).allSatisfy(\.valid)
            && (plot?.steps?.count ?? 0) <= 96 && (plot?.steps ?? []).allSatisfy(\.valid)
            && (plot?.activeCalories?.count ?? 0) <= 96 && (plot?.activeCalories ?? []).allSatisfy(\.valid)
            && (plot?.activeCalories30m?.count ?? 0) <= 48
            && (plot?.activeCalories30m ?? []).allSatisfy { $0.valid(maxIntervalMillis: 1800001) }
            && (plot?.activeCalories30mIntervalMinutes == nil || plot?.activeCalories30mIntervalMinutes == 30)
    }
    var heartRateRange: ClosedRange<Double> {
        let points = heartRate ?? []
        let lower = Swift.max(0, floor(((points.map(\.min).min() ?? 55) - 5) / 10) * 10)
        let upper = Swift.max(lower + 20, ceil(((points.map(\.max).max() ?? 75) + 5) / 10) * 10)
        return lower...upper
    }
}

struct Dashboard: Codable {
    let schemaVersion: Int
    let serverAt: Double
    let latest: Reading?
    let readings: [Reading]
    var metrics: Metrics?
    var comparison: Comparison?
    var analysis: Analysis?
    var dailyAnalysis: Analysis?
    var rollingAnalysis: Analysis?
    var manualAnalysis: ManualAnalysisState?
    var activity: ActivityData?
    var events: [LifestyleEvent]?
    var eventsTruncated: Bool?
    var glucosePlotUpperBound: Double { max(12, (readings.map(\.value).max() ?? 10) + 1) }

    static func decode(_ data: Data) throws -> Dashboard {
        let result = try JSONDecoder().decode(Dashboard.self, from: data)
        guard result.schemaVersion == 1, result.serverAt.isFinite && result.serverAt > 0,
              result.readings.count <= 10000,
              result.readings.allSatisfy({ $0.value.isFinite && $0.value > 0 && $0.value <= 60 && $0.sourceAt.isFinite }),
              result.latest.map({ $0.value.isFinite && $0.value > 0 && $0.value <= 60 && $0.sourceAt.isFinite }) ?? true,
              result.activity?.valid ?? true,
              (result.events?.count ?? 0) <= 500, (result.events ?? []).allSatisfy(\.valid),
              Set((result.events ?? []).map(\.id)).count == (result.events?.count ?? 0),
              [result.analysis, result.dailyAnalysis, result.rollingAnalysis].compactMap({ $0 }).allSatisfy(\.valid)
        else { throw MirrorError.invalidResponse }
        return result
    }
}

struct CachedDashboard: Codable {
    let fetchedAt: Date
    let dashboard: Dashboard
}

enum MirrorError: LocalizedError {
    case invalidConfiguration, invalidResponse, authentication, unavailable
    var errorDescription: String? {
        switch self {
        case .invalidConfiguration: return "请设置 HTTPS 服务地址和只读令牌。"
        case .invalidResponse: return "服务返回的数据格式不正确，已保留上次数据。"
        case .authentication: return "服务拒绝访问，请检查只读令牌。"
        case .unavailable: return "暂时连接不到服务，已保留上次数据。"
        }
    }
}

func metricText(_ value: Double?, suffix: String = "", decimals: Int = 1) -> String {
    guard let value, value.isFinite else { return "—" }
    return String(format: "%.*f", decimals, value) + suffix
}

struct PlotPoint: Identifiable {
    let date: Date
    let value: Double
    let segment: Int
    var id: Date { date }
}

func observedPoints(_ readings: [Reading]) -> [PlotPoint] {
    let ordered = readings.sorted { $0.sourceAt < $1.sourceAt }
    var previous: Date?
    var segment = 0
    return ordered.map { reading in
        if let previous, reading.date.timeIntervalSince(previous) > 600 { segment += 1 }
        previous = reading.date
        return PlotPoint(date: reading.date, value: reading.value, segment: segment)
    }
}
