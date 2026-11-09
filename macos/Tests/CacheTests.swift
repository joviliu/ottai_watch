import Foundation

@main
struct CacheTests {
    static func main() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("ottai-cache-test-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: directory) }
        let file = directory.appendingPathComponent("dashboard.json")
        assert(SnapshotStore.load(at: file) == nil)
        let reading = Reading(sourceAt: 1_800_000_000_000, value: 6.2, trend: "→")
        let dashboard = Dashboard(schemaVersion: 1, serverAt: 1_800_000_000_000, latest: reading, readings: [reading])
        let cached = CachedDashboard(fetchedAt: Date(), dashboard: dashboard)
        try SnapshotStore.save(cached, at: file)
        assert(SnapshotStore.load(at: file)?.dashboard.latest?.value == 6.2)
        let attributes = try FileManager.default.attributesOfItem(atPath: file.path)
        assert(attributes[.posixPermissions] as? Int == 0o600)
        try Data("{}".utf8).write(to: file)
        assert(SnapshotStore.load(at: file) == nil)
        try Data(repeating: 65, count: 4_100_001).write(to: file)
        assert(SnapshotStore.load(at: file) == nil)
        print("Private host cache roundtrip, permissions and corrupt/oversize rejection passed")
    }
}
