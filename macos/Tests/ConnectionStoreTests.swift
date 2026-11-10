import Foundation
import Darwin

@main
struct ConnectionStoreTests {
    static func main() throws {
        let manager = FileManager.default
        let directory = manager.temporaryDirectory.appendingPathComponent("ottai-config-test-\(UUID().uuidString)")
        try manager.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        defer { try? manager.removeItem(at: directory) }
        let file = directory.appendingPathComponent("private/connection.json")
        let configuration = ConnectionConfiguration(baseURL: "https://example.invalid/ottai/", readToken: "test-read-token-only")
        let privileged = ConnectionConfiguration(baseURL: "https://example.invalid/ottai", readToken: "read-only", analysisToken: String(repeating:"a",count:32))
        let checked = try privileged.validated(); assert(checked.analysisToken != nil)
        expectFailure { _ = try ConnectionConfiguration(baseURL: "https://example.invalid", readToken: "r", analysisToken: "short").validated() }
        let store = ConnectionStore(url: file)
        assert(store.current == nil)
        try store.save(configuration)
        let persisted = try ConnectionStore.readConfiguration(from: file, requirePrivateDirectory: true)
        assert(persisted.baseURL == "https://example.invalid/ottai")
        assert(store.current == persisted)
        let folderMode = try manager.attributesOfItem(atPath: file.deletingLastPathComponent().path)[.posixPermissions] as! NSNumber
        let fileMode = try manager.attributesOfItem(atPath: file.path)[.posixPermissions] as! NSNumber
        assert(folderMode.intValue == 0o700 && fileMode.intValue == 0o600)
        try manager.removeItem(at: file)
        assert(store.current == persisted, "refresh must keep the in-memory configuration")
        assert(ConnectionStore(url: file).current == nil, "a new process must not fall back to the old credential store")
        try store.save(configuration)
        let link = directory.appendingPathComponent("linked.json")
        try manager.createSymbolicLink(at: link, withDestinationURL: file)
        expectFailure { _ = try ConnectionStore.readConfiguration(from: link) }
        expectFailure { try ConnectionStore(url: link).save(configuration) }
        let folderLink = directory.appendingPathComponent("linked-folder")
        try manager.createSymbolicLink(at: folderLink, withDestinationURL: file.deletingLastPathComponent())
        expectFailure { _ = try ConnectionStore.readConfiguration(from: folderLink.appendingPathComponent("connection.json")) }
        expectFailure { try ConnectionStore(url: folderLink.appendingPathComponent("connection.json")).save(configuration) }
        try manager.setAttributes([.posixPermissions: 0o644], ofItemAtPath: file.path)
        expectFailure { _ = try ConnectionStore.readConfiguration(from: file) }
        try manager.setAttributes([.posixPermissions: 0o600], ofItemAtPath: file.path)
        try Data(repeating: 65, count: 16385).write(to: file)
        expectFailure { _ = try ConnectionStore.readConfiguration(from: file) }
        expectFailure { _ = try ConnectionConfiguration(baseURL: "http://example.invalid", readToken: "test-token").validated() }
        expectFailure { _ = try ConnectionConfiguration(baseURL: "https://example.invalid", readToken: "bad\ntoken").validated() }
        let appDirectory = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().appendingPathComponent("App")
        for source in try manager.contentsOfDirectory(at: appDirectory, includingPropertiesForKeys: nil) where source.pathExtension == "swift" {
            let text = try String(contentsOf: source, encoding: .utf8)
            assert(!text.contains("SecItem") && !text.contains("import Security"), "no automatic system credential access")
        }
        print("Mac connection checks passed: private permissions, memory cache, symlink/size rejection, safe headers, no system credential API")
    }

    static func expectFailure(_ operation: () throws -> Void) {
        do { try operation(); fatalError("invalid configuration accepted") }
        catch {}
    }
}
