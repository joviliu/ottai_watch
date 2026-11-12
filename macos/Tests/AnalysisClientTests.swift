import Foundation

final class AnalysisFixtureProtocol: URLProtocol, @unchecked Sendable {
    static var handler: ((URLRequest, Data) throws -> (Int, Data))!
    static var calls: [(URLRequest, Data)] = []
    static var delay = 0.0
    private var stopped = false
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        var body = request.httpBody ?? Data()
        if let stream = request.httpBodyStream {
            stream.open(); defer { stream.close() }
            var buffer = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable {
                let n = stream.read(&buffer, maxLength: buffer.count)
                if n <= 0 { break }
                body.append(buffer, count: n)
            }
        }
        Self.calls.append((request, body))
        do {
            let (status, payload) = try Self.handler(request, body)
            DispatchQueue.global().asyncAfter(deadline: .now()+Self.delay) { [self] in
                guard !stopped else { return }
                client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
                client?.urlProtocol(self, didLoad: payload)
                client?.urlProtocolDidFinishLoading(self)
            }
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() { stopped = true }
}

@main
struct AnalysisClientTests {
    @MainActor static func main() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("ottai-analysis-client-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        defer { try? FileManager.default.removeItem(at: folder) }
        let store = ConnectionStore(url: folder.appendingPathComponent("connection.json"))
        let credential = ConnectionConfiguration(baseURL: "https://fixture.invalid/ottai", readToken: "fixture-read", analysisToken: String(repeating: "a", count: 40))
        try store.save(credential)
        let cache = folder.appendingPathComponent("dashboard.json")
        let now = Date().timeIntervalSince1970 * 1000
        var dashboard = Dashboard(schemaVersion: 1, serverAt: now, latest: nil, readings: [],
            rollingAnalysis: Analysis(status: "ready", summary: "Current"),
            manualAnalysis: ManualAnalysisState(eligible: true, status: "ready", reason: "合成可分析状态"))
        try SnapshotStore.save(CachedDashboard(fetchedAt: Date(), dashboard: dashboard), at: cache)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [AnalysisFixtureProtocol.self]
        let model = AppModel(connectionStore: store, snapshotURL: cache, session: URLSession(configuration: configuration), automaticallyRefresh: false, reloadWidgets: {})
        var posts = 0
        AnalysisFixtureProtocol.handler = { request, body in
            if request.httpMethod == "POST" {
                posts += 1
                assert(request.url?.path == "/ottai/api/v1/analysis")
                assert(request.value(forHTTPHeaderField: "Authorization") == "Bearer " + credential.analysisToken!)
                assert(body.isEmpty && request.value(forHTTPHeaderField: "Content-Type") == nil,
                    "blank text must preserve the existing zero-byte request, never JSON null or an empty object")
                return (200, Data(#"{"reason":"复用已有分析"}"#.utf8))
            }
            assert(request.url?.path == "/ottai/api/v1/dashboard" && body.isEmpty)
            return (200, try JSONEncoder().encode(dashboard))
        }
        model.updateAnalysisContext(" \n\t ")
        assert(AnalysisFixtureProtocol.calls.isEmpty, "typing must never make a request")
        await model.analyzeRecent()
        assert(posts == 1 && !model.analyzing)

        dashboard.manualAnalysis = ManualAnalysisState(eligible: false, status: "ready", reason: "当前快照已有分析", eligibleWithContext: true, reasonWithContext: "可结合补充信息分析最近24小时。")
        model.snapshot = CachedDashboard(fetchedAt: Date(), dashboard: dashboard)
        model.updateAnalysisContext("")
        assert(!model.canAnalyze)
        let submitted = "饭后散步\n是否影响这段血糖？😀"
        model.updateAnalysisContext("  " + submitted + " \n")
        assert(model.canAnalyze && model.analysisReason.contains("补充信息"))
        AnalysisFixtureProtocol.delay = 0.04
        AnalysisFixtureProtocol.handler = { request, body in
            if request.httpMethod == "POST" {
                posts += 1
                assert(request.value(forHTTPHeaderField: "Content-Type") == "application/json")
                let payload = try JSONSerialization.jsonObject(with: body) as! [String: String]
                assert(payload == ["userContext": submitted], "only the trimmed submission belongs in the manual request")
                dashboard.rollingAnalysis = Analysis(status: "ready", summary: "Current", reportId: String(repeating: "a", count: 64), userContext: submitted, userResponse: "**合成回答**：先比较相近餐食与活动时点。", userResponseSources: [])
                return (202, Data(#"{"reason":"正在分析"}"#.utf8))
            }
            return (200, try JSONEncoder().encode(dashboard))
        }
        let contextual = Task { await model.analyzeRecent() }
        for _ in 0..<50 { if posts == 2 { break }; try await Task.sleep(for: .milliseconds(2)) }
        model.updateAnalysisContext("下一次的问题草稿")
        await contextual.value
        assert(posts == 2 && model.analysisContext == "下一次的问题草稿")
        assert(model.snapshot?.dashboard.rollingAnalysis?.userContext == submitted,
            "the returned response must stay associated with its submitted question rather than the current draft")
        let pinned = DetailReportSelection(kind: "rolling", reportId: dashboard.rollingAnalysis!.reportId!, parentReport: model.snapshot?.dashboard.rollingAnalysis)
        dashboard.rollingAnalysis?.userContext = "更新报告的问题"
        model.snapshot = CachedDashboard(fetchedAt: Date(), dashboard: dashboard)
        assert(pinned.parentReport?.userContext == submitted, "detail selection must retain its original question and response")
        AnalysisFixtureProtocol.delay = 0
        let retainedQuestion = model.snapshot?.dashboard.rollingAnalysis?.userContext
        AnalysisFixtureProtocol.handler = { request, body in
            assert(request.httpMethod == "GET" && body.isEmpty)
            var malformed = dashboard
            malformed.rollingAnalysis?.userResponseSources = [AnalysisSource(title: "unsafe", url: "file:///etc/passwd")]
            return (200, try JSONEncoder().encode(malformed))
        }
        await model.refresh()
        assert(model.snapshot?.dashboard.rollingAnalysis?.userContext == retainedQuestion && model.message.contains("格式不正确"),
            "unsafe context response from HTTPS must preserve the previously validated report")

        model.updateAnalysisContext(String(repeating: "😀", count: 1000))
        assert(model.analysisContextValid && model.canAnalyze, "limit is Unicode codepoints, not bytes or UTF-16 units")
        let beforeInvalid = AnalysisFixtureProtocol.calls.count
        model.updateAnalysisContext(String(repeating: "e\u{301}", count: 501))
        assert(!model.analysisContextValid && !model.canAnalyze, "combined graphemes still count as separate Unicode codepoints")
        await model.analyzeRecent()
        assert(AnalysisFixtureProtocol.calls.count == beforeInvalid)
        model.updateAnalysisContext("bad\u{0}text")
        assert(!model.analysisContextValid && !model.canAnalyze)
        dashboard.manualAnalysis = ManualAnalysisState(eligible: true, status: "ready", reason: "合成旧服务")
        model.snapshot = CachedDashboard(fetchedAt: Date(), dashboard: dashboard)
        model.updateAnalysisContext("旧服务仍可补充")
        assert(model.canAnalyze, "absent context eligibility must fall back to legacy eligibility")
        dashboard.manualAnalysis = ManualAnalysisState(eligible: false, status: "running", reason: "正在分析", eligibleWithContext: false)
        model.snapshot = CachedDashboard(fetchedAt: Date(), dashboard: dashboard)
        assert(!model.canAnalyze, "supplementary text cannot bypass server coverage, cooldown or concurrency gates")

        dashboard.manualAnalysis = ManualAnalysisState(eligible: true, status: "ready", reason: "可分析")
        model.snapshot = CachedDashboard(fetchedAt: Date(), dashboard: dashboard)
        model.updateAnalysisContext("旧连接的草稿")
        AnalysisFixtureProtocol.delay = 0.08
        AnalysisFixtureProtocol.handler = { request, _ in
            if request.httpMethod == "POST" { posts += 1; return (202, Data(#"{"reason":"旧连接已提交"}"#.utf8)) }
            var current = dashboard
            current.rollingAnalysis = Analysis(status: "ready", summary: "New connection")
            return (200, try JSONEncoder().encode(current))
        }
        let pending = Task { await model.analyzeRecent() }
        for _ in 0..<50 { if posts == 3 { break }; try await Task.sleep(for: .milliseconds(2)) }
        AnalysisFixtureProtocol.delay = 0
        await model.configure(url: credential.baseURL, token: "changed-read", analysisToken: String(repeating: "b", count: 40))
        await model.configure(url: credential.baseURL, token: credential.readToken, analysisToken: credential.analysisToken)
        model.updateAnalysisContext("新连接的草稿")
        await pending.value
        assert(model.analysisContext == "新连接的草稿" && model.snapshot?.dashboard.rollingAnalysis?.summary == "New connection")
        assert(!model.analysisMessage.contains("旧连接") && !model.analyzing)
        let afterChange = AnalysisFixtureProtocol.calls.count
        try await Task.sleep(for: .milliseconds(100))
        assert(AnalysisFixtureProtocol.calls.count == afterChange, "old analysis must not poll or mutate the new connection")

        AnalysisFixtureProtocol.delay = 0.08
        let pendingRefresh = Task { await model.refresh() }
        try await Task.sleep(for: .milliseconds(5))
        await model.configure(url: credential.baseURL, token: "changed-again", analysisToken: credential.analysisToken)
        assert(model.analysisContext.isEmpty, "credential changes on the same URL must clear the prior draft")
        await pendingRefresh.value
        AnalysisFixtureProtocol.delay = 0
        AnalysisFixtureProtocol.handler = { _, _ in throw URLError(.notConnectedToInternet) }
        model.updateAnalysisContext("离线切换前的草稿")
        await model.configure(url: credential.baseURL, token: credential.readToken, analysisToken: credential.analysisToken)
        assert(model.snapshot == nil && model.analysisContext.isEmpty && !FileManager.default.fileExists(atPath: cache.path),
            "failed refresh of a new connection must not retain the prior connection's report in memory or on disk")
        print("Mac context client: blank/trimmed JSON bodies, GET-only typing, Unicode bounds, optional eligibility, submitted-question pinning and credential-change guards passed")
    }
}
