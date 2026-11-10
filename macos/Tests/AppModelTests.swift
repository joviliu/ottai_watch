import Foundation

final class EventFixtureProtocol: URLProtocol, @unchecked Sendable {
    static var handler: ((URLRequest) throws -> (Int, Data))!
    static var requests = 0
    static var bodies: [[String: Any]] = []
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests += 1
        do {
            if request.httpMethod == "POST" {
                let data: Data
                if let body = request.httpBody { data = body }
                else if let stream = request.httpBodyStream {
                    stream.open(); defer { stream.close() }
                    var body = Data(), bytes = [UInt8](repeating: 0, count: 4096)
                    while stream.hasBytesAvailable { let n = stream.read(&bytes, maxLength: bytes.count); if n <= 0 { break }; body.append(bytes, count: n) }
                    data = body
                } else { data = Data() }
                Self.bodies.append(try JSONSerialization.jsonObject(with: data) as! [String: Any])
            }
            let (status, body) = try Self.handler(request)
            client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: body)
            client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}
}

@main
struct AppModelTests {
    @MainActor static func main() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("ottai-event-client-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        defer { try? FileManager.default.removeItem(at: folder) }
        let connection = ConnectionStore(url: folder.appendingPathComponent("connection.json"))
        let credential = ConnectionConfiguration(baseURL: "https://fixture.invalid/ottai", readToken: "fixture-read", analysisToken: String(repeating: "a", count: 40))
        try connection.save(credential)
        let cache = folder.appendingPathComponent("dashboard.json")
        let now = Date().timeIntervalSince1970 * 1000
        var dashboard = Dashboard(schemaVersion: 1, serverAt: now, latest: nil, readings: [],
            dailyAnalysis: Analysis(status: "ready", summary: "Yesterday", periodStart: now-172800000, periodEnd: now-86400000),
            rollingAnalysis: Analysis(status: "ready", summary: "Current", periodStart: now-86400000, periodEnd: now))
        try SnapshotStore.save(CachedDashboard(fetchedAt: Date(), dashboard: dashboard), at: cache)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [EventFixtureProtocol.self]
        let session = URLSession(configuration: configuration)
        let model = AppModel(connectionStore: connection, snapshotURL: cache, session: session,
                             automaticallyRefresh: false, reloadWidgets: {})
        assert(model.canEditEvents)
        var event = LifestyleEvent(id: "client-event-1234", type: .meal, at: now-600000, note: "Lunch",
            meal: MealDetails(foods: "Synthetic rice and greens", estimatedKcalMin: 400, estimatedKcalMax: 550, source: "photo_estimate"))
        var saved = event; saved.updatedAt = now
        EventFixtureProtocol.handler = { request in
            if request.httpMethod == "GET" {
                assert(request.url?.path == "/ottai/api/v1/dashboard")
                assert(request.value(forHTTPHeaderField: "Authorization") == "Bearer fixture-read")
                throw URLError(.notConnectedToInternet)
            }
            assert(request.url?.path == "/ottai/api/v1/events")
            assert(request.value(forHTTPHeaderField: "Authorization") == "Bearer " + String(repeating: "a", count: 40))
            return (200, try JSONSerialization.data(withJSONObject: ["ok": true, "event": JSONSerialization.jsonObject(with: JSONEncoder().encode(saved))]))
        }
        try await model.saveEvent(event)
        assert(model.snapshot?.dashboard.events?.first == saved, "Server-confirmed event survives a failed dashboard refresh")
        assert(model.snapshot?.dashboard.rollingAnalysis?.dataStale == true && model.snapshot?.dashboard.dailyAnalysis?.dataStale != true)
        assert(SnapshotStore.load(at: cache)?.dashboard.events?.first == saved)
        assert(EventFixtureProtocol.bodies.last?["id"] as? String == event.id)
        assert(EventFixtureProtocol.bodies.last?["updatedAt"] == nil && EventFixtureProtocol.bodies.last?["expectedUpdatedAt"] == nil)

        event = saved; event.note = "Changed note"
        EventFixtureProtocol.handler = { _ in (409, Data(#"{"error":"event_conflict"}"#.utf8)) }
        do { try await model.saveEvent(event); fatalError("Conflict accepted") } catch EventWriteError.conflict {}
        assert(model.snapshot?.dashboard.events?.first == saved && !model.eventSaving)
        assert(EventFixtureProtocol.bodies.last?["expectedUpdatedAt"] as? Double == saved.updatedAt)
        assert(EventFixtureProtocol.bodies.last?["updatedAt"] == nil)
        let meal = EventFixtureProtocol.bodies.last?["meal"] as! [String: Any]
        assert(meal["source"] as? String == "photo_estimate" && meal["estimatedKcalMin"] as? Double == 400)

        EventFixtureProtocol.handler = { _ in throw URLError(.timedOut) }
        do { try await model.saveEvent(event); fatalError("Timeout accepted") } catch EventWriteError.unavailable {}
        assert(model.snapshot?.dashboard.events?.first == saved && !model.eventSaving)
        let retryID = EventFixtureProtocol.bodies.last?["id"] as? String
        var edited = event; edited.updatedAt = now+1
        dashboard.events = [edited]
        EventFixtureProtocol.handler = { request in
            if request.httpMethod == "GET" { return (200, try JSONEncoder().encode(dashboard)) }
            return (200, try JSONSerialization.data(withJSONObject: ["ok": true, "event": JSONSerialization.jsonObject(with: JSONEncoder().encode(edited))]))
        }
        try await model.saveEvent(event)
        assert(EventFixtureProtocol.bodies.last?["id"] as? String == retryID && model.snapshot?.dashboard.events?.first == edited)

        EventFixtureProtocol.handler = { _ in (400, Data(#"{"error":"invalid_event"}"#.utf8)) }
        do { try await model.deleteEvent(edited); fatalError("Invalid deletion accepted") } catch EventWriteError.invalid {}
        assert(model.snapshot?.dashboard.events?.first == edited)
        dashboard.events = []
        EventFixtureProtocol.handler = { request in
            if request.httpMethod == "GET" { return (200, try JSONEncoder().encode(dashboard)) }
            assert(request.url?.path == "/ottai/api/v1/events/delete")
            return (200, Data(#"{"ok":true}"#.utf8))
        }
        try await model.deleteEvent(edited)
        assert(model.snapshot?.dashboard.events?.isEmpty == true)
        assert(EventFixtureProtocol.bodies.last?["expectedUpdatedAt"] as? Double == edited.updatedAt)

        try connection.save(ConnectionConfiguration(baseURL: credential.baseURL, readToken: credential.readToken))
        let before = EventFixtureProtocol.requests
        assert(!model.canEditEvents)
        do { try await model.saveEvent(event); fatalError("Read-only write accepted") } catch EventWriteError.permission {}
        assert(EventFixtureProtocol.requests == before)
        print("Mac event client: capability/path/body, revision conflict, stable retry ID, meal preservation, confirmed-cache retention and soft delete passed")
    }
}
