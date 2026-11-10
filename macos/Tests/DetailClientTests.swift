import Foundation

final class DetailFixtureProtocol: URLProtocol, @unchecked Sendable {
    static var handler: ((URLRequest, Data) throws -> (Int, Data))!
    static var calls: [URLRequest] = []
    static var delay = 0.0
    private var stopped = false
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.calls.append(request)
        var body = request.httpBody ?? Data()
        if let stream = request.httpBodyStream {
            stream.open(); defer { stream.close() }
            var buffer = [UInt8](repeating: 0, count: 1024)
            while stream.hasBytesAvailable {
                let n = stream.read(&buffer, maxLength: buffer.count)
                if n <= 0 { break }
                body.append(buffer, count: n)
            }
        }
        do {
            let (status, payload) = try Self.handler(request, body)
            DispatchQueue.global().asyncAfter(deadline: .now()+Self.delay) { [self] in
                if stopped { return }
                client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
                client?.urlProtocol(self, didLoad: payload)
                client?.urlProtocolDidFinishLoading(self)
            }
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() { stopped = true }
}

@main
struct DetailClientTests {
    static let reportID = String(repeating: "a", count: 64)
    static let source = DetailSource(id: "fixture-source", title: "合成来源", url: "https://example.invalid/paper")
    static let report = DetailedReport(title: "合成详细解读", summary: "合成资料，只用于界面与网络检查。",
        sections: (0..<3).map { DetailSection(title: "观察\($0+1)", text: "一段合成的病例解读。", sourceIds: [source.id]) },
        hypotheses: [DetailHypothesis(title: "一个可验证的解释", support: "合成支持线索", against: "合成替代解释", verification: "合成验证办法", confidence: "moderate", sourceIds: [source.id])],
        actions: [DetailAction(title: "合成建议", text: "以相近情境作一次可比较记录。")], limitations: [], sources: [source])
    static func state(_ status: String, eligible: Bool = false, kind: String = "rolling", id: String = reportID, stale: Bool = false) -> DetailAnalysisState {
        DetailAnalysisState(schemaVersion: 1, kind: kind, reportId: id, status: status, eligible: eligible, reason: "合成状态",
            periodStart: 1794200000000, periodEnd: 1794286400000, dataStale: stale, report: status == "ready" ? report : nil)
    }
    @MainActor static func main() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("ottai-detail-client-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        defer { try? FileManager.default.removeItem(at: folder) }
        let store = ConnectionStore(url: folder.appendingPathComponent("connection.json"))
        let credential = ConnectionConfiguration(baseURL: "https://fixture.invalid/ottai", readToken: "fixture-read", analysisToken: String(repeating: "p", count: 40))
        try store.save(credential)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [DetailFixtureProtocol.self]
        let session = URLSession(configuration: configuration)
        let selected = DetailReportSelection(kind: "rolling", reportId: reportID)
        func controller(_ selection: DetailReportSelection? = nil) -> DetailAnalysisModel {
            DetailAnalysisModel(selection: selection ?? selected, connectionStore: store, session: session, pollInterval: .milliseconds(5), pollCount: 4)
        }
        assert(report.valid)
        _ = try DetailAnalysisState.decode(JSONEncoder().encode(state("ready")), for: selected)
        for malformed in [state("ready", kind: "daily"), state("ready", id: String(repeating: "b", count: 64))] {
            do { _ = try DetailAnalysisState.decode(JSONEncoder().encode(malformed), for: selected); fatalError("wrong report bound to detail viewer") }
            catch MirrorError.invalidResponse {}
        }
        let object = try JSONSerialization.jsonObject(with: JSONEncoder().encode(state("ready"))) as! [String: Any]
        for mutation in ["unknown-reference", "oversized-section", "unsafe-link"] {
            var data = object, body = data["report"] as! [String: Any]
            if mutation == "unsafe-link" { var sources = body["sources"] as! [[String: Any]]; sources[0]["url"] = "file:///etc/passwd"; body["sources"] = sources }
            else { var sections = body["sections"] as! [[String: Any]]; if mutation == "unknown-reference" { sections[0]["sourceIds"] = ["invented-source"] } else { sections[0]["text"] = String(repeating: "x", count: 3501) }; body["sections"] = sections }
            data["report"] = body
            do { _ = try DetailAnalysisState.decode(JSONSerialization.data(withJSONObject: data), for: selected); fatalError("invalid detailed report accepted") }
            catch MirrorError.invalidResponse {}
        }

        var gets = 0, posts = 0, requested = false
        DetailFixtureProtocol.handler = { request, body in
            assert(request.url?.path == "/ottai/api/v1/analysis/detail")
            assert(request.timeoutInterval >= 45, "detail context preparation must not inherit the dashboard's20s request timeout")
            if request.httpMethod == "POST" {
                posts += 1; requested = true
                assert(request.value(forHTTPHeaderField: "Authorization") == "Bearer " + credential.analysisToken!)
                assert(request.value(forHTTPHeaderField: "Content-Type") == "application/json")
                let payload = try JSONSerialization.jsonObject(with: body) as! [String: String]
                assert(payload == ["kind": "rolling", "reportId": reportID])
                return (202, try JSONEncoder().encode(state("running")))
            }
            gets += 1
            assert(body.isEmpty && request.value(forHTTPHeaderField: "Authorization") == "Bearer fixture-read")
            let query = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)!.queryItems!
            assert(query.contains(URLQueryItem(name: "kind", value: "rolling")) && query.contains(URLQueryItem(name: "reportId", value: reportID)))
            return (200, try JSONEncoder().encode(requested ? state(gets >= 3 ? "ready" : "running") : state("available", eligible: true)))
        }
        let first = controller()
        await first.open()
        assert(first.canGenerate && posts == 0, "opening a viewer must never start a paid analysis")
        await first.generate()
        for _ in 0..<50 { if first.state?.status == "ready" { break }; try await Task.sleep(for: .milliseconds(10)) }
        assert(posts == 1 && first.state?.status == "ready" && first.state?.report?.title == report.title)
        await first.refreshStatus()
        assert(posts == 1, "GET polling and refresh must never repeat POST")
        first.stop()

        let dailyID = String(repeating: "b", count: 64)
        DetailFixtureProtocol.handler = { request, body in
            assert(request.httpMethod == "GET" && body.isEmpty)
            let query = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)!.queryItems!
            assert(query.contains(URLQueryItem(name: "kind", value: "daily")) && query.contains(URLQueryItem(name: "reportId", value: dailyID)))
            return (200, try JSONEncoder().encode(state("ready", kind: "daily", id: dailyID)))
        }
        let daily = controller(DetailReportSelection(kind: "daily", reportId: dailyID))
        await daily.open()
        assert(daily.state?.kind == "daily" && daily.state?.reportId == dailyID && posts == 1)
        daily.stop()

        DetailFixtureProtocol.handler = { request, _ in
            assert(request.httpMethod == "GET")
            return (200, try JSONEncoder().encode(state("ready", eligible: true, stale: true)))
        }
        let updated = controller(); await updated.open()
        assert(updated.state?.report != nil && updated.canGenerate && updated.generationTitle == "生成新版解读")
        updated.stop()

        DetailFixtureProtocol.handler = { request, _ in
            if request.httpMethod == "POST" { posts += 1; throw URLError(.timedOut) }
            return (200, try JSONEncoder().encode(state("available", eligible: true)))
        }
        let uncertain = controller(); await uncertain.open(); await uncertain.generate()
        let afterUnknown = posts
        await uncertain.generate(); await uncertain.refreshStatus()
        assert(uncertain.unconfirmed && !uncertain.canGenerate && posts == afterUnknown)
        uncertain.stop()

        DetailFixtureProtocol.handler = { request, _ in
            if request.httpMethod == "POST" { posts += 1; return (202, try JSONEncoder().encode(state("running"))) }
            return (200, try JSONEncoder().encode(state("available", eligible: true)))
        }
        let closing = controller(); await closing.open(); await closing.generate(); closing.stop()
        let afterClose = DetailFixtureProtocol.calls.count
        try await Task.sleep(for: .milliseconds(40))
        assert(DetailFixtureProtocol.calls.count == afterClose, "closing a viewer must stop its polling")

        DetailFixtureProtocol.delay = 0.1
        DetailFixtureProtocol.handler = { _, _ in (200, try JSONEncoder().encode(state("ready"))) }
        let changing = controller()
        let pending = Task { await changing.open() }
        try await Task.sleep(for: .milliseconds(20))
        try store.save(ConnectionConfiguration(baseURL: "https://other.invalid", readToken: "other-read"))
        await pending.value
        assert(changing.state == nil && changing.message.contains("连接已更改"))
        changing.stop()
        DetailFixtureProtocol.delay = 0

        let reader = controller()
        DetailFixtureProtocol.handler = { request, _ in
            assert(request.httpMethod == "GET")
            return (200, try JSONEncoder().encode(state("available", eligible: true)))
        }
        await reader.open()
        let before = DetailFixtureProtocol.calls.count
        await reader.generate()
        assert(!reader.canGenerate && DetailFixtureProtocol.calls.count == before)
        reader.stop()
        print("Mac detail client: GET-only open/cache/poll, explicit JSON POST capability, pinned IDs, stale regeneration, unknown-result suppression, close/config guards and model/source bounds passed")
    }
}
