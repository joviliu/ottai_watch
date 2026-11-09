import SwiftUI
import AppKit

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private var dashboardWindow: NSWindow?
    private var dashboardObserver: NSObjectProtocol?

    func applicationDidFinishLaunching(_ notification: Notification) {
        dashboardObserver = DistributedNotificationCenter.default().addObserver(forName: SingleInstance.showDashboard, object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor in self?.showDashboard() }
        }
    }

    func application(_ application: NSApplication, open urls: [URL]) {
        guard urls.contains(where: { $0.scheme == "ottaimirror" && $0.host == "dashboard" }) else { return }
        showDashboard()
    }

    private func showDashboard() {
        if dashboardWindow == nil {
            let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 700, height: 800),
                                  styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
            window.title = "血糖镜像"
            window.contentView = NSHostingView(rootView: DashboardView(model: AppModel.shared))
            window.isReleasedWhenClosed = false
            window.center()
            dashboardWindow = window
        }
        NSApplication.shared.activate(ignoringOtherApps: true)
        dashboardWindow?.makeKeyAndOrderFront(nil)
    }
}

@main
struct OttaiMirrorApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @StateObject private var model = AppModel.shared

    init() {
        if !SingleInstance.claim() { exit(0) }
    }

    var body: some Scene {
        MenuBarExtra {
            MenuContent(model: model)
        } label: {
            Image(nsImage: StatusBadge.menuImage(reading: model.latest, now: model.now))
                .accessibilityLabel("血糖 \(model.latest?.display ?? "暂无")，\(model.stale ? "待更新" : "已更新")")
                .help(model.latest.map { "血糖 \($0.display) mmol/L · \($0.displayTrend) · \(DisplayTime.time($0.date))" } ?? "血糖镜像 · 等待数据")
        }.menuBarExtraStyle(.window)
    }
}
