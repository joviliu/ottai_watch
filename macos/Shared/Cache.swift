import Foundation

enum SnapshotStore {
    static let kind = "OttaiGlucoseWidget"
    static var localURL: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("OttaiMirror/dashboard.json")
    }

    static func load(at url: URL = localURL) -> CachedDashboard? {
        guard let file = try? FileHandle(forReadingFrom: url) else { return nil }
        defer { try? file.close() }
        guard let data = try? file.read(upToCount: 4_100_001), data.count <= 4_100_000,
              let snapshot = try? JSONDecoder().decode(CachedDashboard.self, from: data),
              (try? Dashboard.decode(JSONEncoder().encode(snapshot.dashboard))) != nil else { return nil }
        return snapshot
    }

    static func save(_ snapshot: CachedDashboard, at url: URL = localURL) throws {
        let data = try JSONEncoder().encode(snapshot)
        let manager = FileManager.default
        try manager.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true,
                                    attributes: [.posixPermissions: 0o700])
        try data.write(to: url, options: .atomic)
        try manager.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
    }
}
