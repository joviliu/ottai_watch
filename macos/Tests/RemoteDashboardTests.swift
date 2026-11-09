import Foundation

final class MockDashboardProtocol: URLProtocol, @unchecked Sendable {
    static var status = 200
    static var payload = Data()
    static var failure: Error?
    static var requests = 0
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.requests += 1
        assert(request.httpMethod == "GET")
        assert(request.url?.path == "/ottai/api/v1/dashboard")
        assert(request.value(forHTTPHeaderField: "Authorization") == "Bearer unit-test-read-only")
        if let error = Self.failure { client?.urlProtocol(self, didFailWithError: error); return }
        let response = HTTPURLResponse(url: request.url!, statusCode: Self.status, httpVersion: "HTTP/1.1", headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Self.payload)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@main
struct RemoteDashboardTests {
    static func main() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("ottai-remote-test-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        defer { try? FileManager.default.removeItem(at: folder) }
        let remote = RemoteDashboard(testDirectory: folder, protocolClasses: [MockDashboardProtocol.self])
        func load() -> WidgetRemoteResult {
            let ready = DispatchSemaphore(value: 0)
            var result: WidgetRemoteResult?
            remote.load { result = $0; ready.signal() }
            assert(ready.wait(timeout: .now() + 5) == .success)
            return result!
        }
        assert(load().category == .notConfigured)
        let config = folder.appendingPathComponent("connection.json")
        try Data(#"{"baseURL":"https://example.invalid/ottai","readToken":"unit-test-read-only"}"#.utf8).write(to: config)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: config.path)
        MockDashboardProtocol.payload = Data(#"{"schemaVersion":1,"serverAt":1800000000000,"latest":{"sourceAt":1800000000000,"value":6.2,"trend":"→"},"readings":[{"sourceAt":1800000000000,"value":6.2,"trend":"→"}]}"#.utf8)
        let success = load()
        assert(success.category == .ok && success.snapshot?.dashboard.latest?.value == 6.2)
        let cache = folder.appendingPathComponent("widget-dashboard.json")
        let attributes = try FileManager.default.attributesOfItem(atPath: cache.path)
        assert(attributes[.posixPermissions] as? Int == 0o600)
        MockDashboardProtocol.failure = URLError(.timedOut)
        let timeout = load()
        assert(timeout.category == .timedOut && timeout.snapshot?.dashboard.latest?.value == 6.2)
        MockDashboardProtocol.failure = nil
        MockDashboardProtocol.status = 401
        assert(load().category == .authentication)
        MockDashboardProtocol.status = 302
        assert(load().category == .redirectRejected)
        MockDashboardProtocol.status = 200
        MockDashboardProtocol.payload = Data(repeating: 65, count: 2_000_001)
        assert(load().category == .responseTooLarge)
        MockDashboardProtocol.payload = Data("{}".utf8)
        assert(load().category == .invalidResponse)
        let before = MockDashboardProtocol.requests
        try FileManager.default.setAttributes([.posixPermissions: 0o644], ofItemAtPath: config.path)
        assert(load().category == .invalidConfiguration && MockDashboardProtocol.requests == before)
        try FileManager.default.removeItem(at: config)
        try FileManager.default.createSymbolicLink(at: config, withDestinationURL: cache)
        assert(load().category == .invalidConfiguration)
        print("Sandbox-local Widget network checks passed: HTTPS/path/auth, cache, timeout, 401, redirect, size, JSON, permissions and symlink")
    }
}
