import AppKit
import OSLog

@MainActor
enum SingleInstance {
    private static var processLock: ProcessLock?
    private static let logger = Logger(subsystem: "com.joviliu.ottai.mirror", category: "instance")
    static let showDashboard = Notification.Name("com.joviliu.ottai.mirror.showDashboard")

    static func claim() -> Bool {
        let current = NSRunningApplication.current
        let others = NSRunningApplication.runningApplications(withBundleIdentifier: "com.joviliu.ottai.mirror")
            .filter { $0.processIdentifier != current.processIdentifier && !$0.isTerminated }
        // Older releases did not hold the lock. Prefer an existing earlier process during upgrade.
        let older = others.filter {
            if let left = $0.launchDate, let right = current.launchDate, left != right { return left < right }
            return $0.processIdentifier < current.processIdentifier
        }
        if let existing = older.min(by: { ($0.launchDate ?? .distantPast) < ($1.launchDate ?? .distantPast) }) {
            forward(to: existing)
            return false
        }
        do {
            processLock = try ProcessLock(at: ConnectionStore.location.deletingLastPathComponent().appendingPathComponent("instance.lock"))
            return true
        } catch ProcessLock.Failure.busy {
            forward(to: others.first)
            return false
        } catch {
            logger.error("instance_lock_unavailable")
            return false
        }
    }

    private static func forward(to existing: NSRunningApplication?) {
        DistributedNotificationCenter.default().postNotificationName(showDashboard, object: nil, userInfo: nil, deliverImmediately: true)
        existing?.activate(options: [])
        guard let application = existing?.bundleURL else { logger.info("duplicate_launch_notified"); return }
        let configuration = NSWorkspace.OpenConfiguration()
        configuration.activates = true
        configuration.createsNewApplicationInstance = false
        let completed = DispatchSemaphore(value: 0)
        NSWorkspace.shared.open([URL(string: "ottaimirror://dashboard")!], withApplicationAt: application, configuration: configuration) { _, _ in
            completed.signal()
        }
        let deadline = Date().addingTimeInterval(2)
        while completed.wait(timeout: .now()) == .timedOut && Date() < deadline { RunLoop.current.run(until: Date().addingTimeInterval(0.05)) }
        logger.info("duplicate_launch_forwarded")
    }
}
