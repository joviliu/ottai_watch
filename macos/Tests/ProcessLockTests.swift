import Foundation

@main
struct ProcessLockTests {
    static func main() throws {
        if CommandLine.arguments.count == 3, CommandLine.arguments[1] == "--contend" {
            do { _ = try ProcessLock(at: URL(fileURLWithPath: CommandLine.arguments[2])); exit(9) }
            catch ProcessLock.Failure.busy { exit(0) }
        }
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("ottai-lock-test-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: directory) }
        let url = directory.appendingPathComponent("instance.lock")
        var primary: ProcessLock? = try ProcessLock(at: url)
        assert(primary != nil)
        let child = Process()
        child.executableURL = URL(fileURLWithPath: CommandLine.arguments[0])
        child.arguments = ["--contend", url.path]
        try child.run(); child.waitUntilExit()
        assert(child.terminationStatus == 0, "second process must not acquire the same per-user lock")
        primary = nil
        let next = try ProcessLock(at: url)
        withExtendedLifetime(next) {}
        print("Cross-process instance lock checks passed: duplicate blocked and lock released on close")
    }
}
