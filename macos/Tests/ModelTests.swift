import Foundation

@main
struct ModelTests {
    static func main() throws {
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        let calendar = Calendar(identifier: .gregorian)
        for hour in [0, 6, 12, 18, 23] {
            let date = calendar.date(from: DateComponents(year: 2026, month: 11, day: 9, hour: hour, minute: 7))!
            assert(DisplayTime.time(date) == String(format: "%02d:07", hour), "time must always use HH:mm")
        }
        let fresh = Reading(sourceAt: now.addingTimeInterval(-300).timeIntervalSince1970 * 1000, value: 6.4, trend: "↘")
        assert(!fresh.isStale(at: now))
        assert(fresh.isStale(at: now.addingTimeInterval(301)))
        assert(Reading(sourceAt: now.addingTimeInterval(121).timeIntervalSince1970 * 1000, value: 6, trend: "→").isStale(at: now))
        let series = [fresh, Reading(sourceAt: fresh.sourceAt - 900_000, value: 6.1, trend: "→"),
                      Reading(sourceAt: fresh.sourceAt - 300_000, value: 6.3, trend: "↗")]
        let points = observedPoints(series)
        assert(points.count == 3 && points[0].segment == 0 && points[1].segment == 0 && points[2].segment == 0)
        let withGap = observedPoints([fresh, Reading(sourceAt: fresh.sourceAt - 901_000, value: 6.1, trend: "→")])
        assert(withGap.map(\.segment) == [0, 1], "do not join long missing intervals")
        let json = """
        {"schemaVersion":1,"serverAt":1800000000000,"latest":{"sourceAt":1799999700000,"value":6.4,"trend":"↘"},"readings":[],
         "metrics":{"mean":null,"coveragePercent":0,"inRangePercent":null},"comparison":{"daysAvailable":2,"timezone":"Asia/Shanghai","points":[]},
         "analysis":{"status":"waiting","generatedAt":null,"summary":null,"sections":[],"limitations":["历史不足"],"sources":[]}}
        """
        let dashboard = try Dashboard.decode(Data(json.utf8))
        assert(dashboard.metrics?.mean == nil && dashboard.metrics?.coveragePercent == 0)
        assert(dashboard.latest?.display == "6.4" && dashboard.analysis?.status == "waiting")
        assert(dashboard.comparison?.timezone == "Asia/Shanghai")
        for value in [0.1, 0.5, 40.0, 45.0, 60.0] {
            let valid = json.replacingOccurrences(of: "\"value\":6.4", with: "\"value\":\(value)")
            let decoded = try Dashboard.decode(Data(valid.utf8))
            assert(decoded.latest?.value == value)
        }
        for value in [0.0, -0.1, 60.1] {
            let invalid = json.replacingOccurrences(of: "\"value\":6.4", with: "\"value\":\(value)")
            do { _ = try Dashboard.decode(Data(invalid.utf8)); fatalError("invalid range accepted") }
            catch MirrorError.invalidResponse {}
        }
        let longTrend = String(repeating: "↗", count: 32)
        let trend = Reading(sourceAt: fresh.sourceAt, value: 45, trend: longTrend)
        assert(trend.trend == longTrend && trend.displayTrend == "↗")
        assert(Reading(sourceAt: fresh.sourceAt, value: 6, trend: "unknown-text").displayTrend == "?")
        for (trend, symbol) in [("↑↑", "chevron.up.2"), ("↑", "arrow.up"), ("↗", "arrow.up.right"), ("→", "arrow.right"),
                                ("↘", "arrow.down.right"), ("↓", "arrow.down"), ("↓↓", "chevron.down.2"), ("unknown", "questionmark")] {
            let state = Reading(sourceAt: fresh.sourceAt, value: 6.2, trend: trend)
            assert(state.statusTrendSymbol == symbol && state.trend == trend)
        }
        let bucket = ComparisonPoint(minuteOfDay: 30, median: 6.3, p25: 6, p75: 6.6, sampleDays: 3)
        let oneDay = ComparisonPoint(minuteOfDay: 60, median: 7, p25: 7, p75: 7, sampleDays: 1)
        assert(Comparison(daysAvailable: 2, points: [bucket]).plotPoints.isEmpty)
        assert(Comparison(daysAvailable: 3, points: [bucket, oneDay]).plotPoints.count == 1)
        assert(Analysis(status: "waiting", summary: "正在积累数据").displayStatus == "积累数据中")
        assert(Analysis(status: "error", summary: "尚无报告").displayStatus == "分析失败")
        assert(Analysis(status: "error", reportDate: "2026-01-01", summary: "Previous report").displayStatus.contains("旧报告"))
        assert(Analysis(status: "ready", dataStale: true).displayStatus == "旧报告")
        for malformed in [json.replacingOccurrences(of: "\"schemaVersion\":1", with: "\"schemaVersion\":2"),
                          json.replacingOccurrences(of: "\"value\":6.4", with: "\"value\":99") ] {
            do { _ = try Dashboard.decode(Data(malformed.utf8)); fatalError("invalid response accepted") }
            catch MirrorError.invalidResponse {}
        }
        let cached = CachedDashboard(fetchedAt: now, dashboard: dashboard)
        let restored = try JSONDecoder().decode(CachedDashboard.self, from: JSONEncoder().encode(cached))
        assert(restored.fetchedAt == now && restored.dashboard.latest?.sourceAt == dashboard.latest?.sourceAt)
        let base = URL(string: "https://example.invalid/ottai")!
        assert(base.appendingPathComponent("api/v1/dashboard").path == "/ottai/api/v1/dashboard")
        assert(metricText(nil) == "—" && metricText(98, suffix: "%", decimals: 0) == "98%")
        print("Mac model checks passed: schema, missing-data semantics, staleness, chart gaps, cache round-trip, path prefix")
    }
}
